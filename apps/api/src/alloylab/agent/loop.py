"""The autonomous campaign loop (plan section 28).

    state -> decision -> validate -> execute -> persist -> update models -> repeat

Problem-agnostic: everything scientific is delegated to the campaign's
Problem adapter (`alloylab.problems`). Agent reasoning (LLM or heuristic) only
*chooses* actions; the job executor guarantees the calculations actually
happen and records provenance.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.base import get_session_factory
from ..db.models import AgentRun, Calculation, Campaign
from ..events import emit_agent_event as emit
from ..jobs import JobExecutor, create_executor
from .decisions import ActionType, ScientificDecision

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CampaignRunnerRegistry:
    """Tracks the asyncio task running each campaign's autonomous loop."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._executor: JobExecutor | None = None

    @property
    def executor(self):
        if self._executor is None:
            self._executor = create_executor(get_settings())
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

RUN_ACTIONS = (ActionType.RUN_MONTE_CARLO, ActionType.RUN_STRUCTURE_ENERGY)


async def run_campaign_loop(campaign_id: str, agent_run_id: str, executor: JobExecutor) -> None:
    from ..problems import get_problem

    session_factory = get_session_factory()
    iteration = 0

    async with session_factory() as session:
        campaign = await session.get(Campaign, campaign_id)
        assert campaign is not None
        max_iterations = campaign.simulation_budget * 3 + 10
        problem = get_problem(campaign)
        decider = problem.decider(campaign)
        await problem.initialize(session, campaign)
        await emit(
            session,
            campaign_id,
            "CAMPAIGN_STARTED",
            agent_run_id=agent_run_id,
            action=f"Autonomous run started (problem: {problem.problem_type}, "
            f"strategy: {campaign.strategy})",
        )

    while iteration < max_iterations:
        iteration += 1
        async with session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            if campaign is None or campaign.status != "RUNNING":
                break

            state = await problem.build_state(session, campaign)
            decision = await decider.decide(state)
            decision = problem.validate(state, decision)

            await emit(
                session,
                campaign_id,
                "AGENT_DECISION",
                agent_run_id=agent_run_id,
                hypothesis=decision.hypothesis,
                reasoning_summary="; ".join(decision.evidence) or None,
                action=problem.describe_action(decision),
                payload=decision.model_dump(mode="json"),
            )

            if decision.action_type == ActionType.FINISH_CAMPAIGN:
                await _finish(session, campaign, agent_run_id, decision)
                finalize = getattr(problem, "finalize", None)
                if finalize is not None:
                    await finalize(session, campaign, agent_run_id)
                await _persist_report(session, campaign, agent_run_id)
                break

            if decision.action_type == ActionType.ABANDON_CALCULATION:
                failed = await session.get(Calculation, decision.retry_calculation_id)
                if failed is not None:
                    failed.resolution = "abandoned"
                    await session.commit()
                continue

            if decision.action_type == ActionType.RETRY_CALCULATION:
                calc_ids = [await _create_retry(session, campaign, decision)]
            elif decision.action_type in RUN_ACTIONS:
                calc_ids = await problem.create_calculations(session, campaign, decision)
            else:
                continue

        # Execute outside the session: the executor manages its own sessions.
        await asyncio.gather(*(executor.run_calculation(cid) for cid in calc_ids))

        async with session_factory() as session:
            campaign = await session.get(Campaign, campaign_id)
            if campaign is None:
                break
            await _refresh_budget(session, campaign)
            await problem.update_models(session, campaign, agent_run_id)

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


async def _create_retry(
    session: AsyncSession, campaign: Campaign, decision: ScientificDecision
) -> str:
    original = await session.get(Calculation, decision.retry_calculation_id)
    assert original is not None
    params = dict(original.input_parameters)
    changed: dict = {}
    for key, factor in (decision.adjusted_parameters or {}).items():
        base_name = key.removesuffix("_factor")
        if base_name in params and isinstance(params[base_name], (int, float)):
            new_value = params[base_name] * factor
            params[base_name] = (
                int(new_value) if isinstance(params[base_name], int) else float(new_value)
            )
            changed[base_name] = params[base_name]
    if not changed:
        changed = {"is_retry": True}
    params["is_retry"] = True
    params["seed"] = int(params.get("seed", 0)) + 1
    retry = Calculation(
        campaign_id=campaign.id,
        structure_id=original.structure_id,
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


async def _persist_report(session: AsyncSession, campaign: Campaign, agent_run_id: str) -> None:
    """Milestone 9 'explain results': build and store the final report."""
    from ..report import build_report, llm_narrative

    report = await build_report(session, campaign)
    try:
        prose = await llm_narrative(report, get_settings().agent_model)
        if prose:
            report["llm_narrative"] = prose
    except Exception as exc:  # noqa: BLE001 — narrative is optional
        report["llm_narrative_error"] = str(exc)
    campaign.report = report
    await session.commit()
    await emit(
        session,
        campaign.id,
        "REPORT_GENERATED",
        agent_run_id=agent_run_id,
        action="Final scientific report generated",
        tool_output_reference=f"campaign_report:{campaign.id}",
        payload={"key_results": report["key_results"], "n_limitations": len(report["limitations"])},
    )


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
