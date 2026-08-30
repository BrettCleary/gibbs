"""Ising V0 problem adapter: locate the critical region of the 2D Ising model."""

from __future__ import annotations

import asyncio

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.surrogate import ResponseSurrogate

from ..agent.decisions import ActionType, ScientificDecision
from ..agent.state import ScientificState, build_scientific_state
from ..agent.strategies import Decider, HeuristicDecider, stable_seed
from ..db.models import Calculation, Campaign, SurrogateModel
from ..events import emit_agent_event
from .base import MAX_TARGETS_PER_DECISION

DEFAULT_EQUILIBRATION_SWEEPS = 800
DEFAULT_MEASUREMENT_SWEEPS = 2000

ISING_LLM_INSTRUCTIONS = """\
You are an autonomous computational materials scientist running a Monte Carlo
campaign on the 2D Ising model. Your objective: locate the critical-temperature
region (the susceptibility peak) as precisely as possible within a finite
simulation budget.

Rules:
- You never compute physical quantities yourself; every number you cite must
  come from the provided state or tools.
- Prefer measurements that most reduce uncertainty about the susceptibility
  peak location. Early on, cover the temperature range; later, concentrate
  around the suspected peak and wherever the surrogate ensemble disagrees.
- If a calculation failed and has not been resolved, decide whether to RETRY
  it (typically with longer equilibration) or ABANDON it. A run that already
  failed once as a retry should be abandoned.
- Propose at most 3 temperatures per decision (action_type RUN_MONTE_CARLO)
  and stay inside the allowed range.
- If the budget is exhausted, or the Tc uncertainty is below the target, or you
  judge further experiments to have low expected value, FINISH the campaign and
  say why.
- Fill hypothesis / evidence / uncertainty / expected_information_gain with
  concise, concrete scientific statements grounded in the numbers you saw.
"""


class IsingProblem:
    problem_type = "ising_v0"

    async def initialize(self, session: AsyncSession, campaign: Campaign) -> None:
        return None

    async def build_state(self, session: AsyncSession, campaign: Campaign) -> ScientificState:
        return await build_scientific_state(session, campaign)

    def decider(self, campaign: Campaign) -> Decider:
        if campaign.strategy == "agent":
            from ..agent.llm import LLMDecider

            return LLMDecider(
                instructions=ISING_LLM_INSTRUCTIONS,
                render_state=_render_ising_state,
                action_types=(ActionType.RUN_MONTE_CARLO,),
            )
        return HeuristicDecider(campaign.strategy, seed=stable_seed(campaign.id))

    def validate(
        self, state: ScientificState, decision: ScientificDecision
    ) -> ScientificDecision:
        if decision.action_type == ActionType.RUN_MONTE_CARLO:
            temps = [
                float(min(max(t, state.temperature_min), state.temperature_max))
                for t in decision.temperatures
            ]
            cleaned: list[float] = []
            for t in temps:
                if all(abs(t - u) > 1e-6 for u in cleaned):
                    cleaned.append(t)
            limit = min(MAX_TARGETS_PER_DECISION, state.budget_remaining)
            cleaned = cleaned[:limit]
            if not cleaned:
                fallback = state.suggested_uncertainty_temperature or 0.5 * (
                    state.temperature_min + state.temperature_max
                )
                cleaned = [float(fallback)]
            decision = decision.model_copy(update={"temperatures": cleaned})
        if decision.action_type in (ActionType.RETRY_CALCULATION, ActionType.ABANDON_CALCULATION):
            known = {f.calculation_id for f in state.unresolved_failures}
            if decision.retry_calculation_id not in known:
                raise ValueError(
                    f"decision references unknown failed calculation "
                    f"{decision.retry_calculation_id!r}"
                )
        return decision

    async def create_calculations(
        self, session: AsyncSession, campaign: Campaign, decision: ScientificDecision
    ) -> list[str]:
        n_existing = (
            await session.execute(
                select(func.count())
                .select_from(Calculation)
                .where(Calculation.campaign_id == campaign.id)
            )
        ).scalar_one()
        calcs: list[Calculation] = []
        for i, temperature in enumerate(decision.temperatures):
            calc = Calculation(
                campaign_id=campaign.id,
                calculation_type="MONTE_CARLO",
                engine="alloyscience.ising.IsingSimulator",
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
        await session.flush()
        ids = [c.id for c in calcs]
        await session.commit()
        return ids

    async def update_models(
        self, session: AsyncSession, campaign: Campaign, agent_run_id: str | None
    ) -> None:
        calcs = (
            (
                await session.execute(
                    select(Calculation)
                    .where(
                        Calculation.campaign_id == campaign.id,
                        Calculation.status == "SUCCEEDED",
                    )
                    .order_by(Calculation.created_at)
                )
            )
            .scalars()
            .all()
        )
        if len(calcs) < ResponseSurrogate.MIN_POINTS:
            return
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
            return

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
        await emit_agent_event(
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

    async def finalize(self, session: AsyncSession, campaign: Campaign, agent_run_id: str | None) -> None:
        """Record the located critical-temperature region as a FINAL_RECOMMENDATION."""
        latest = (
            await session.execute(
                select(SurrogateModel)
                .where(SurrogateModel.campaign_id == campaign.id)
                .order_by(SurrogateModel.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        metrics = latest.validation_metrics if latest else {}
        tc, tc_std = metrics.get("tc_mean"), metrics.get("tc_std")
        if tc is None:
            action = "No critical-temperature estimate could be fitted within the budget."
        else:
            action = (
                f"RECOMMENDATION: critical temperature Tc = {tc:.4f} ± {tc_std:.4f} J/k_B "
                f"(surrogate v{latest.version} on {metrics.get('n_training_points', 0)} measurements)"
            )
        await emit_agent_event(
            session, campaign.id, "FINAL_RECOMMENDATION", agent_run_id=agent_run_id, action=action,
            payload={"tc_mean": tc, "tc_std": tc_std},
        )

    def describe_action(self, decision: ScientificDecision) -> str:
        if decision.action_type == ActionType.RUN_MONTE_CARLO:
            temps = ", ".join(f"{t:.3f}" for t in decision.temperatures)
            return f"Run Monte Carlo at T = {temps}"
        return _generic_action_text(decision)


def _generic_action_text(decision: ScientificDecision) -> str:
    if decision.action_type == ActionType.RETRY_CALCULATION:
        return f"Retry failed calculation {decision.retry_calculation_id} with adjusted settings"
    if decision.action_type == ActionType.ABANDON_CALCULATION:
        return f"Abandon failed calculation {decision.retry_calculation_id}"
    return f"Finish campaign: {decision.stopping_rationale or 'no rationale given'}"


def _render_ising_state(state: ScientificState) -> str:
    import json

    measurements = [
        {
            "calculation_id": m.calculation_id,
            "T": round(m.temperature, 4),
            "chi": round(m.susceptibility, 3),
            "chi_err": round(m.susceptibility_err, 3),
        }
        for m in state.measurements
    ]
    payload = {
        "objective": state.objective,
        "temperature_range": [state.temperature_min, state.temperature_max],
        "lattice_size": state.lattice_size,
        "budget": {
            "total": state.budget_total,
            "used": state.budget_used,
            "remaining": state.budget_remaining,
        },
        "target_tc_uncertainty": state.target_uncertainty,
        "measurements": measurements,
        "unresolved_failures": [f.model_dump() for f in state.unresolved_failures],
        "latest_surrogate": state.latest_model.model_dump() if state.latest_model else None,
        "highest_uncertainty_temperature_suggestion": state.suggested_uncertainty_temperature,
    }
    return (
        "Current scientific state (all numbers computed by deterministic tools):\n"
        + json.dumps(payload, indent=2)
        + "\nDecide the next action."
    )
