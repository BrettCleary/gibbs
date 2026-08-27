"""Phase-diagram problem adapter (Milestone 5): map T_c(x) of a hidden CE.

The campaign's expensive experiment is one canonical Monte Carlo run at a
chosen (composition slice, temperature) on the hidden cluster expansion. The
heat-capacity peak per slice locates the order/disorder boundary; bootstrap
ensemble spread quantifies its uncertainty; the agent spends its MC budget on
the most uncertain boundaries.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.phase import (
    PhaseAcquisitionState,
    SliceMeasurements,
    estimate_slice_boundary,
    propose_phase_point,
)
from alloyscience.surrogate import ResponseSurrogate

from ..agent.decisions import ActionType, ScientificDecision
from ..agent.state import (
    BaseScientificState,
    ModelSummary,
    budget_used,
    latest_surrogate_model,
    load_campaign_calculations,
    unresolved_failures,
)
from ..agent.strategies import (
    Decider,
    check_stopping,
    handle_failures,
    model_summary_text,
    stable_seed,
)
from ..db.models import Calculation, Campaign, SurrogateModel
from ..events import emit_agent_event
from .base import MAX_TARGETS_PER_DECISION
from .ising import _generic_action_text

DEFAULT_TRIAL_STEPS = 20_000
SUPERCELL_REPEAT = 4

PHASE_RETRY_ADJUSTMENT = {"n_trial_steps_factor": 3.0}
PHASE_RETRY_REASON = "Tripled MC trial steps to address a non-equilibrated chain."

PHASE_LLM_INSTRUCTIONS = """\
You are an autonomous computational materials scientist mapping the
composition-temperature phase diagram of an FCC {elements} alloy governed by a
hidden cluster expansion. At fixed composition slices you may run canonical
Monte Carlo at temperatures of your choice (in Kelvin); each run is expensive
and returns the heat capacity (whose peak marks the order/disorder transition)
and the Warren-Cowley short-range-order parameter.

Rules:
- You never compute physical quantities yourself; every number you cite must
  come from the provided state.
- Goal: estimate the transition temperature T_c(x) of every slice as precisely
  as possible within the budget. Early on, cover each slice's temperature
  range; later, concentrate where the per-slice bootstrap surrogate is most
  uncertain, prioritising the slice with the largest T_c uncertainty.
- Each RUN_MONTE_CARLO decision targets exactly one composition slice (set
  `composition` to one of the configured slices) with at most 3 temperatures.
- If a calculation failed and has not been resolved, decide whether to RETRY
  it (typically with more trial steps) or ABANDON it. A run that already
  failed once as a retry should be abandoned.
- If the budget is exhausted, or every boundary is below the target
  uncertainty, FINISH the campaign and say why.
- Fill hypothesis / evidence / uncertainty / expected_information_gain with
  concise, concrete scientific statements grounded in the numbers you saw.
"""


class PhaseMeasurement(BaseModel):
    calculation_id: str
    temperature: float
    heat_capacity: float
    heat_capacity_err: float
    sro: float


class PhaseSlice(BaseModel):
    x: float
    measurements: list[PhaseMeasurement] = Field(default_factory=list)
    tc_mean: float | None = None
    tc_std: float | None = None
    tc_edge_pinned: bool = False  # peak at window edge: Tc is a bound, not a location
    suggested_temperature: float | None = None


class PhaseState(BaseScientificState):
    temperature_min: float
    temperature_max: float
    slices: list[PhaseSlice] = Field(default_factory=list)
    suggested_slice_x: float | None = None
    suggested_temperature: float | None = None


def _slices_from_config(campaign: Campaign) -> list[float]:
    return [float(x) for x in (campaign.problem_config or {}).get("slices", [0.25, 0.5, 0.75])]


def _acquisition_state(state: PhaseState) -> PhaseAcquisitionState:
    return PhaseAcquisitionState(
        t_min=state.temperature_min,
        t_max=state.temperature_max,
        slices=[
            SliceMeasurements(
                x=s.x,
                temperatures=[m.temperature for m in s.measurements],
                heat_capacities=[m.heat_capacity for m in s.measurements],
                heat_capacity_errs=[m.heat_capacity_err for m in s.measurements],
            )
            for s in state.slices
        ],
        remaining_budget=state.budget_remaining,
    )


async def build_phase_state(session: AsyncSession, campaign: Campaign) -> PhaseState:
    calcs = await load_campaign_calculations(session, campaign.id)
    slice_xs = _slices_from_config(campaign)
    slices = [PhaseSlice(x=x) for x in slice_xs]
    by_x = {round(s.x, 6): s for s in slices}

    for c in calcs:
        if c.status != "SUCCEEDED" or not c.output or c.calculation_type != "MONTE_CARLO":
            continue
        key = round(float(c.input_parameters.get("composition", -1)), 6)
        if key not in by_x:
            continue
        by_x[key].measurements.append(
            PhaseMeasurement(
                calculation_id=c.id,
                temperature=float(c.input_parameters["temperature"]),
                heat_capacity=float(c.output["heat_capacity"]),
                heat_capacity_err=float(c.output["heat_capacity_err"]),
                sro=float(c.output["sro"]),
            )
        )
    for s in slices:
        s.measurements.sort(key=lambda m: m.temperature)

    seed = stable_seed(campaign.id)
    for s in slices:
        data = SliceMeasurements(
            x=s.x,
            temperatures=[m.temperature for m in s.measurements],
            heat_capacities=[m.heat_capacity for m in s.measurements],
            heat_capacity_errs=[m.heat_capacity_err for m in s.measurements],
        )
        est = estimate_slice_boundary(
            data, campaign.temperature_min, campaign.temperature_max, seed=seed
        )
        if est is not None:
            s.tc_mean, s.tc_std = est.mean, est.std
            s.tc_edge_pinned = est.edge_pinned
            surrogate = ResponseSurrogate(
                data.temperatures, data.heat_capacities, data.heat_capacity_errs, seed=seed
            )
            s.suggested_temperature = surrogate.suggest_peak_refinement(
                campaign.temperature_min,
                campaign.temperature_max,
                exclude=data.temperatures,
            )

    latest = await latest_surrogate_model(session, campaign.id)
    latest_model = None
    if latest is not None:
        metrics = latest.validation_metrics
        latest_model = ModelSummary(
            version=latest.version,
            n_training_points=metrics.get("n_training_points", 0),
            uncertainty_metric=metrics.get("max_tc_std"),
            summary_text=(
                f"Phase boundary v{latest.version}: "
                f"{metrics.get('n_fitted_slices', 0)}/{len(slice_xs)} slices fitted, "
                f"max σ(Tc) = {metrics.get('max_tc_std'):.0f} K"
                if metrics.get("max_tc_std") is not None
                else f"Phase boundary v{latest.version}"
            ),
        )

    # Global suggestion: slice with the largest boundary uncertainty (or the
    # least-measured slice while bootstrapping).
    suggested_x = suggested_t = None
    counts = [len(s.measurements) for s in slices]
    if slices:
        if min(counts) < ResponseSurrogate.MIN_POINTS:
            i = int(np.argmin(counts))
        else:
            stds = [s.tc_std if s.tc_std is not None else float("inf") for s in slices]
            i = int(np.argmax(stds))
        suggested_x = slices[i].x
        suggested_t = slices[i].suggested_temperature

    used = budget_used(calcs)
    return PhaseState(
        campaign_id=campaign.id,
        objective=campaign.objective,
        strategy=campaign.strategy,
        budget_total=campaign.simulation_budget,
        budget_used=used,
        budget_remaining=max(campaign.simulation_budget - used, 0),
        target_uncertainty=campaign.target_uncertainty,
        unresolved_failures=unresolved_failures(
            calcs,
            lambda c: (
                f"MC at x={float(c.input_parameters.get('composition', 0)):.3f}, "
                f"T={float(c.input_parameters.get('temperature', 0)):.0f} K"
            ),
        ),
        latest_model=latest_model,
        temperature_min=campaign.temperature_min,
        temperature_max=campaign.temperature_max,
        slices=slices,
        suggested_slice_x=suggested_x,
        suggested_temperature=suggested_t,
    )


class PhaseHeuristicDecider:
    def __init__(self, strategy_name: str, seed: int = 0):
        self.name = strategy_name
        self._rng = np.random.default_rng(seed)

    async def decide(self, state: PhaseState) -> ScientificDecision:
        # Budget is a hard ceiling: stopping outranks even failure recovery.
        decision = check_stopping(state) or handle_failures(
            state, PHASE_RETRY_ADJUSTMENT, PHASE_RETRY_REASON
        )
        if decision is not None:
            return decision
        i, t = propose_phase_point(_acquisition_state(state), self.name, self._rng)
        x = state.slices[i].x
        rationale = {
            "random": "Baseline: uniformly random (x, T) selection.",
            "grid": "Baseline: round-robin slices, bisecting each slice's largest T gap.",
            "uncertainty": "Target the slice with the largest boundary uncertainty, "
            "at the temperature where its surrogate ensemble disagrees most.",
        }[self.name]
        return ScientificDecision(
            hypothesis=f"An MC run at x={x:.3f}, T={t:.0f} K best refines the "
            f"phase boundary. {rationale}",
            evidence=[
                f"{sum(len(s.measurements) for s in state.slices)} completed MC runs",
                model_summary_text(state),
            ],
            uncertainty=model_summary_text(state),
            action_type=ActionType.RUN_MONTE_CARLO,
            composition=x,
            temperatures=[float(t)],
            expected_information_gain=rationale,
        )


class PhaseLLMDecider:
    name = "agent"

    def __init__(self, instructions: str = PHASE_LLM_INSTRUCTIONS):
        from ..agent.llm import LLMDecider

        self._llm = LLMDecider(
            instructions=instructions,
            render_state=render_phase_state,
            action_types=(ActionType.RUN_MONTE_CARLO,),
        )
        self.last_usage = None

    async def decide(self, state: PhaseState) -> ScientificDecision:
        decision = await self._llm.decide(state)
        self.last_usage = self._llm.last_usage
        return decision


def render_phase_state(state: PhaseState) -> str:
    payload = {
        "objective": state.objective,
        "temperature_range_K": [state.temperature_min, state.temperature_max],
        "budget": {
            "total": state.budget_total,
            "used": state.budget_used,
            "remaining": state.budget_remaining,
        },
        "target_boundary_uncertainty_K": state.target_uncertainty,
        "slices": [
            {
                "x": s.x,
                "tc_estimate_K": (
                    {"mean": round(s.tc_mean), "std": round(s.tc_std)}
                    if s.tc_mean is not None
                    else None
                ),
                "highest_uncertainty_temperature": s.suggested_temperature,
                "measurements": [
                    {
                        "T": round(m.temperature),
                        "C_kB": round(m.heat_capacity, 3),
                        "C_err": round(m.heat_capacity_err, 3),
                        "sro": round(m.sro, 3),
                    }
                    for m in s.measurements
                ],
            }
            for s in state.slices
        ],
        "unresolved_failures": [f.model_dump() for f in state.unresolved_failures],
        "latest_model": state.latest_model.model_dump() if state.latest_model else None,
    }
    return (
        "Current scientific state (all numbers computed by deterministic tools):\n"
        + json.dumps(payload, indent=2)
        + "\nDecide the next action."
    )


class PhaseProblem:
    problem_type = "phase_v2"

    async def initialize(self, session: AsyncSession, campaign: Campaign) -> None:
        return None

    async def build_state(self, session: AsyncSession, campaign: Campaign) -> PhaseState:
        return await build_phase_state(session, campaign)

    def decider(self, campaign: Campaign) -> Decider:
        if campaign.strategy == "agent":
            pair = "-".join((campaign.problem_config or {}).get("elements", ["Ni", "Al"]))
            return PhaseLLMDecider(instructions=PHASE_LLM_INSTRUCTIONS.replace("{elements}", pair))
        return PhaseHeuristicDecider(campaign.strategy, seed=stable_seed(campaign.id))

    def validate(self, state: PhaseState, decision: ScientificDecision) -> ScientificDecision:
        if decision.action_type == ActionType.RUN_MONTE_CARLO:
            slice_xs = [s.x for s in state.slices]
            x = decision.composition
            if x is None:
                x = state.suggested_slice_x if state.suggested_slice_x is not None else slice_xs[0]
            # Snap to the nearest configured slice.
            x = min(slice_xs, key=lambda sx: abs(sx - float(x)))
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
                fallback = state.suggested_temperature or 0.5 * (
                    state.temperature_min + state.temperature_max
                )
                cleaned = [float(fallback)]
            decision = decision.model_copy(update={"composition": x, "temperatures": cleaned})
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
        calcs = await load_campaign_calculations(session, campaign.id)
        n_existing = len(calcs)
        created: list[Calculation] = []
        for i, temperature in enumerate(decision.temperatures):
            calc = Calculation(
                campaign_id=campaign.id,
                calculation_type="MONTE_CARLO",
                engine="mchammer.CanonicalEnsemble",
                input_parameters={
                    "composition": float(decision.composition),
                    "temperature": float(temperature),
                    "supercell_repeat": SUPERCELL_REPEAT,
                    "n_trial_steps": DEFAULT_TRIAL_STEPS,
                    "seed": stable_seed(campaign.id) % 100_000 + n_existing + i,
                    "failure_rate": campaign.failure_rate,
                },
            )
            session.add(calc)
            created.append(calc)
        await session.flush()
        ids = [c.id for c in created]
        await session.commit()
        return ids

    async def update_models(
        self, session: AsyncSession, campaign: Campaign, agent_run_id: str | None
    ) -> None:
        state = await build_phase_state(session, campaign)
        training_ids = sorted(
            m.calculation_id for s in state.slices for m in s.measurements
        )
        if len(training_ids) < ResponseSurrogate.MIN_POINTS:
            return
        latest = await latest_surrogate_model(session, campaign.id)
        if latest is not None and latest.training_calculation_ids == training_ids:
            return

        seed = stable_seed(campaign.id)
        grid = np.linspace(campaign.temperature_min, campaign.temperature_max, 61)

        def _fit():
            slices_artifact = []
            for s in state.slices:
                entry: dict = {
                    "x": s.x,
                    "tc_mean": None,
                    "tc_std": None,
                    "tc_edge_pinned": False,
                    "curve_t": [],
                    "curve_mean": [],
                    "curve_std": [],
                }
                if len(s.measurements) >= ResponseSurrogate.MIN_POINTS:
                    surrogate = ResponseSurrogate(
                        [m.temperature for m in s.measurements],
                        [m.heat_capacity for m in s.measurements],
                        [m.heat_capacity_err for m in s.measurements],
                        seed=seed,
                    )
                    pred = surrogate.predict(grid)
                    est = surrogate.estimate_peak(
                        campaign.temperature_min, campaign.temperature_max
                    )
                    entry.update(
                        tc_mean=est.mean,
                        tc_std=est.std,
                        tc_edge_pinned=est.edge_pinned,
                        curve_t=pred.temperatures,
                        curve_mean=pred.mean,
                        curve_std=pred.std,
                    )
                slices_artifact.append(entry)
            return slices_artifact

        slices_artifact = await asyncio.to_thread(_fit)
        fitted = [s for s in slices_artifact if s["tc_mean"] is not None]
        all_fitted = len(fitted) == len(slices_artifact)
        max_tc_std = max((s["tc_std"] for s in fitted), default=None)
        model = SurrogateModel(
            campaign_id=campaign.id,
            type="phase_boundary",
            version=(latest.version + 1) if latest else 1,
            training_calculation_ids=training_ids,
            parameters={"observable": "heat_capacity", "estimator": "bootstrap_peak"},
            validation_metrics={
                # Only meaningful for stopping once every slice has a boundary.
                "max_tc_std": max_tc_std if all_fitted else None,
                "n_fitted_slices": len(fitted),
                "n_training_points": len(training_ids),
            },
            artifact={"slices": slices_artifact},
        )
        session.add(model)
        await session.commit()
        boundary_text = ", ".join(
            (
                f"x={s['x']:.2f}: Tc ≲ {s['tc_mean']:.0f} K (window edge)"
                if s["tc_edge_pinned"]
                else f"x={s['x']:.2f}: Tc={s['tc_mean']:.0f}±{s['tc_std']:.0f} K"
            )
            for s in fitted
        )
        await emit_agent_event(
            session,
            campaign.id,
            "MODEL_UPDATED",
            agent_run_id=agent_run_id,
            action=(
                f"Phase boundary v{model.version} refitted on {len(training_ids)} MC runs "
                f"({len(fitted)}/{len(slices_artifact)} slices): {boundary_text or 'no slice fitted yet'}"
            ),
            tool_output_reference=f"surrogate_model:{model.id}",
            payload={
                "version": model.version,
                "boundaries": [
                    {"x": s["x"], "tc_mean": s["tc_mean"], "tc_std": s["tc_std"]}
                    for s in slices_artifact
                ],
            },
        )

    def describe_action(self, decision: ScientificDecision) -> str:
        if decision.action_type == ActionType.RUN_MONTE_CARLO:
            temps = ", ".join(f"{t:.0f}" for t in decision.temperatures)
            return f"Run canonical MC at x={decision.composition:.3f}, T = {temps} K"
        return _generic_action_text(decision)
