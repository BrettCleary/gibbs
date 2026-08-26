"""The autonomous campaign loop (plan section 28).

    state -> decision -> validate -> execute -> persist -> update models -> repeat

Agent reasoning (LLM or heuristic) only *chooses* actions; the job executor
guarantees the calculations actually happen and records provenance.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.surrogate import ResponseSurrogate

from ..config import get_settings
from ..db.base import get_session_factory
from ..db.models import AgentEvent, AgentRun, Calculation, Campaign, SurrogateModel
from ..events import event_bus
from ..jobs import JobExecutor
from .decisions import ActionType, ScientificDecision
from .state import ScientificState, build_scientific_state
from .strategies import make_decider, stable_seed

logger = logging.getLogger(__name__)

DEFAULT_EQUILIBRATION_SWEEPS = 800
DEFAULT_MEASUREMENT_SWEEPS = 2000
MAX_TEMPERATURES_PER_DECISION = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def emit(
    session: AsyncSession,
    campaign_id: str,
    event_type: str,
    agent_run_id: str | None = None,
    **fields,
) -> AgentEvent:
    event = AgentEvent(
        campaign_id=campaign_id, agent_run_id=agent_run_id, event_type=event_type, **fields
    )
    session.add(event)
    await session.commit()
    await event_bus.publish(
        campaign_id,
        {
            "id": event.id,
            "campaign_id": campaign_id,
            "agent_run_id": agent_run_id,
            "event_type": event_type,
            "hypothesis": event.hypothesis,
            "reasoning_summary": event.reasoning_summary,
            "action": event.action,
            "tool_name": event.tool_name,
            "tool_output_reference": event.tool_output_reference,
            "payload": event.payload,
            "created_at": event.created_at.isoformat(),
        },
    )
    return event


def validate_decision(state: ScientificState, decision: ScientificDecision) -> ScientificDecision:
    """Clamp and sanity-check an agent decision; invalid proposals are repaired."""
    if decision.action_type == ActionType.RUN_MONTE_CARLO:
        temps = [
            float(min(max(t, state.temperature_min), state.temperature_max))
            for t in decision.temperatures
        ]
        # de-duplicate (within a small tolerance) and cap batch size / budget
        cleaned: list[float] = []
        for t in temps:
            if all(abs(t - u) > 1e-6 for u in cleaned):
                cleaned.append(t)
        limit = min(MAX_TEMPERATURES_PER_DECISION, state.budget_remaining)
        cleaned = cleaned[:limit]
        if not cleaned:
            # Repair: fall back to the highest-uncertainty suggestion or range midpoint.
            fallback = state.suggested_uncertainty_temperature or 0.5 * (
                state.temperature_min + state.temperature_max
            )
            cleaned = [float(fallback)]
        decision = decision.model_copy(update={"temperatures": cleaned})
    if decision.action_type in (ActionType.RETRY_CALCULATION, ActionType.ABANDON_CALCULATION):
        known = {f.calculation_id for f in state.unresolved_failures}
        if decision.retry_calculation_id not in known:
            raise ValueError(
                f"decision references unknown failed calculation {decision.retry_calculation_id!r}"
            )
    return decision


class CampaignRunnerRegistry:
    """Tracks the asyncio task running each campaign's autonomous loop."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._executor: JobExecutor | None = None

    @property
    def executor(self) -> JobExecutor:
        if self._executor is None:
            self._executor = JobExecutor(max_concurrent=get_settings().max_concurrent_jobs)
        return self._executor

    def is_running(self, campaign_id: str) -> bool:
        task = self._tasks.get(campaign_id)
        return task is not None and not task.done()

    async def start(self, campaign_id: str, model: str = "heuristic") -> str:
        session_factory = get_session_factory()
        async with session_factory() as session:
            agent_run = AgentRun(campaign_id=campaign_id, model=model)
            session.add(agent_run)
            await session.commit()
            agent_run_id = agent_run.id
        task = asyncio.create_task(self._run_safe(campaign_id, agent_run_id))
        self._tasks[campaign_id] = task
        return agent_run_id

    async def wait(self, campaign_id: str) -> None:
        task = self._tasks.get(campaign_id)
        if task is not None:
            await task

    async def shutdown(self) -> None:
        for task in self._tasks.values():
            task.cancel()
        for task in self._tasks.values():
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._tasks.clear()

    async def _run_safe(self, campaign_id: str, agent_run_id: str) -> None:
        try:
            await run_campaign_loop(campaign_id, agent_run_id, self.executor)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.exception("campaign %s loop crashed", campaign_id)
            session_factory = get_session_factory()
            async with session_factory() as session:
                campaign = await session.get(Campaign, campaign_id)
                if campaign is not None:
                    campaign.status = "FAILED"
                    campaign.stopping_rationale = f"internal error: {exc}"
                agent_run = await session.get(AgentRun, agent_run_id)
                if agent_run is not None:
                    agent_run.status = "FAILED"
                    agent_run.completed_at = _now()
                await session.commit()
                await emit(
                    session,
                    campaign_id,
                    "CAMPAIGN_ERROR",
                    agent_run_id=agent_run_id,
                    action=f"Campaign loop error: {exc}",
                )


runner_registry = CampaignRunnerRegistry()


async def run_campaign_loop(
    campaign_id: str, agent_run_id: str, executor: JobExecutor
) -> None:
    session_factory = get_session_factory()
    iteration = 0

    async with session_factory() as session:
        campaign = await session.get(Campaign, campaign_id)
        assert campaign is not None
        max_iterations = campaign.simulation_budget * 3 + 10
        decider = make_decider(campaign.strategy, campaign_id)
        await emit(
            session,
            campaign_id,
            "CAMPAIGN_STARTED",
            agent_run_id=agent_run_id,
            action=f"Autonomous run started (strategy: {campaign.strategy})",
        )

    while iteration < max_iterations:
        iteration += 1
        async with session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            if campaign is None or campaign.status != "RUNNING":
                break

            state = await build_scientific_state(session, campaign)
            decision = await decider.decide(state)
            decision = validate_decision(state, decision)

            await emit(
                session,
                campaign_id,
                "AGENT_DECISION",
                agent_run_id=agent_run_id,
                hypothesis=decision.hypothesis,
                reasoning_summary="; ".join(decision.evidence) or None,
                action=_describe_action(decision),
                payload=decision.model_dump(mode="json"),
            )

            if decision.action_type == ActionType.FINISH_CAMPAIGN:
                await _finish(session, campaign, agent_run_id, decision)
                break

            if decision.action_type == ActionType.ABANDON_CALCULATION:
                failed = await session.get(Calculation, decision.retry_calculation_id)
                if failed is not None:
                    failed.resolution = "abandoned"
                    await session.commit()
                continue

            if decision.action_type == ActionType.RETRY_CALCULATION:
                calc_ids = [await _create_retry(session, campaign, decision)]
            else:
                calc_ids = await _create_calculations(session, campaign, decision.temperatures)

        # Execute outside the session: the executor manages its own sessions.
        await asyncio.gather(*(executor.run_calculation(cid) for cid in calc_ids))

        async with session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            if campaign is None:
                break
            await _refresh_budget(session, campaign)
            await _update_surrogate(session, campaign, agent_run_id)

    else:
        # Safety valve: too many iterations without a finish decision.
        async with session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            if campaign is not None and campaign.status == "RUNNING":
                campaign.status = "COMPLETED"
                campaign.stopping_rationale = "iteration safety limit reached"
                await session.commit()

    async with session_factory() as session:
        agent_run = await session.get(AgentRun, agent_run_id)
        if agent_run is not None and agent_run.status == "RUNNING":
            agent_run.status = "COMPLETED"
            agent_run.completed_at = _now()
            usage = getattr(decider, "last_usage", None)
            if usage:
                agent_run.token_usage = usage
            await session.commit()


def _describe_action(decision: ScientificDecision) -> str:
    if decision.action_type == ActionType.RUN_MONTE_CARLO:
        temps = ", ".join(f"{t:.3f}" for t in decision.temperatures)
        return f"Run Monte Carlo at T = {temps}"
    if decision.action_type == ActionType.RETRY_CALCULATION:
        return f"Retry failed calculation {decision.retry_calculation_id} with adjusted settings"
    if decision.action_type == ActionType.ABANDON_CALCULATION:
        return f"Abandon failed calculation {decision.retry_calculation_id}"
    return f"Finish campaign: {decision.stopping_rationale or 'no rationale given'}"


async def _create_calculations(
    session: AsyncSession, campaign: Campaign, temperatures: list[float]
) -> list[str]:
    n_existing = (
        await session.execute(
            select(func.count())
            .select_from(Calculation)
            .where(Calculation.campaign_id == campaign.id)
        )
    ).scalar_one()
    calcs: list[Calculation] = []
    for i, temperature in enumerate(temperatures):
        calc = Calculation(
            campaign_id=campaign.id,
            calculation_type="MONTE_CARLO",
            input_parameters={
                "temperature": float(temperature),
                "lattice_size": campaign.lattice_size,
                "n_equilibration_sweeps": DEFAULT_EQUILIBRATION_SWEEPS,
                "n_measurement_sweeps": DEFAULT_MEASUREMENT_SWEEPS,
                "seed": stable_seed(campaign.id) % 100_000 + n_existing + i,
                "failure_rate": campaign.failure_rate,
            },
        )
        session.add(calc)
        calcs.append(calc)
    await session.flush()  # populate ids before reading them
    ids = [c.id for c in calcs]
    await session.commit()
    return ids


async def _create_retry(
    session: AsyncSession, campaign: Campaign, decision: ScientificDecision
) -> str:
    original = await session.get(Calculation, decision.retry_calculation_id)
    assert original is not None
    params = dict(original.input_parameters)
    factor = (decision.adjusted_parameters or {}).get("n_equilibration_sweeps_factor", 3.0)
    changed = {
        "n_equilibration_sweeps": int(
            params.get("n_equilibration_sweeps", DEFAULT_EQUILIBRATION_SWEEPS) * factor
        )
    }
    params.update(changed)
    params["is_retry"] = True
    params["seed"] = int(params.get("seed", 0)) + 1
    retry = Calculation(
        campaign_id=campaign.id,
        calculation_type=original.calculation_type,
        engine=original.engine,
        input_parameters=params,
        retry_of=original.id,
        changed_parameters=changed,
        reason_for_change=decision.reason_for_change,
    )
    original.resolution = "retried"
    session.add(retry)
    await session.commit()
    return retry.id


async def _refresh_budget(session: AsyncSession, campaign: Campaign) -> None:
    used = (
        await session.execute(
            select(func.count())
            .select_from(Calculation)
            .where(
                Calculation.campaign_id == campaign.id,
                Calculation.status.in_(("SUCCEEDED", "FAILED")),
            )
        )
    ).scalar_one()
    campaign.simulations_used = int(used)
    await session.commit()


async def _update_surrogate(
    session: AsyncSession, campaign: Campaign, agent_run_id: str | None
) -> SurrogateModel | None:
    """Refit the response surrogate whenever new successful measurements exist."""
    calcs = (
        (
            await session.execute(
                select(Calculation)
                .where(Calculation.campaign_id == campaign.id, Calculation.status == "SUCCEEDED")
                .order_by(Calculation.created_at)
            )
        )
        .scalars()
        .all()
    )
    if len(calcs) < ResponseSurrogate.MIN_POINTS:
        return None
    training_ids = [c.id for c in calcs]

    latest = (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign.id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and latest.training_calculation_ids == training_ids:
        return latest

    temps = [float(c.input_parameters["temperature"]) for c in calcs]
    chis = [float(c.output["susceptibility"]) for c in calcs]
    errs = [float(c.output["susceptibility_err"]) for c in calcs]

    def _fit():
        surrogate = ResponseSurrogate(temps, chis, errs, seed=stable_seed(campaign.id))
        grid = np.linspace(campaign.temperature_min, campaign.temperature_max, 101)
        pred = surrogate.predict(grid)
        est = surrogate.estimate_peak(campaign.temperature_min, campaign.temperature_max)
        return pred, est, surrogate.bandwidth

    pred, est, bandwidth = await asyncio.to_thread(_fit)
    model = SurrogateModel(
        campaign_id=campaign.id,
        type="response_surrogate",
        version=(latest.version + 1) if latest else 1,
        training_calculation_ids=training_ids,
        parameters={"bandwidth": bandwidth, "n_ensemble": 40},
        validation_metrics={
            "tc_mean": est.mean,
            "tc_std": est.std,
            "n_training_points": len(training_ids),
        },
        artifact={
            "temperatures": pred.temperatures,
            "mean": pred.mean,
            "std": pred.std,
        },
    )
    session.add(model)
    await session.commit()
    await emit(
        session,
        campaign.id,
        "MODEL_UPDATED",
        agent_run_id=agent_run_id,
        action=(
            f"Surrogate v{model.version} fitted on {len(training_ids)} measurements: "
            f"Tc = {est.mean:.4f} ± {est.std:.4f}"
        ),
        tool_output_reference=f"surrogate_model:{model.id}",
        payload={"tc_mean": est.mean, "tc_std": est.std, "version": model.version},
    )
    return model


async def _finish(
    session: AsyncSession,
    campaign: Campaign,
    agent_run_id: str,
    decision: ScientificDecision,
) -> None:
    campaign.status = "COMPLETED"
    campaign.stopping_rationale = decision.stopping_rationale or decision.hypothesis
    await session.commit()
    await emit(
        session,
        campaign.id,
        "CAMPAIGN_COMPLETED",
        agent_run_id=agent_run_id,
        action=f"Campaign completed: {campaign.stopping_rationale}",
        payload={"stopping_rationale": campaign.stopping_rationale},
    )
