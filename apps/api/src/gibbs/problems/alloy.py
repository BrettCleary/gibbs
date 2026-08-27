"""Alloy V1 problem adapter (Milestone 3): hidden binary-alloy Hamiltonian.

The agent must discover which orderings of A/B on the lattice are stable —
formation energies, the convex hull, and the ground-state set — using as few
oracle queries as possible. The hidden interactions live in
campaign.problem_config and are visible only to the executor.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.alloy import AlloyStructure, enumerate_structures
from alloyscience.alloy.cluster_expansion import ClusterExpansionSurrogate
from alloyscience.benchmark import AlloyAcquisitionState, predicted_hull_from_state

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
from ..db.models import Calculation, Campaign, Structure, SurrogateModel
from ..events import emit_agent_event
from .base import MAX_TARGETS_PER_DECISION
from .ising import _generic_action_text

ALLOY_RETRY_ADJUSTMENT = {"max_scf_iterations_factor": 2.0}
ALLOY_RETRY_REASON = (
    "Doubled max SCF iterations and tightened mixing to recover electronic convergence."
)

ALLOY_LLM_INSTRUCTIONS = """\
You are an autonomous computational materials scientist searching a binary
alloy A(1-x)B(x) on a fixed lattice. A hidden Hamiltonian governs structure
energies; you can only learn it through expensive per-structure energy queries
(a simulated DFT oracle). Your objective: identify which ordered structures
are thermodynamically stable (on the formation-energy convex hull) using as
few queries as possible.

Rules:
- You never compute physical quantities yourself; every number you cite must
  come from the provided state or tools.
- A cluster-expansion surrogate is refit after each batch; its per-structure
  uncertainty (ensemble std) and LOOCV error tell you where the model is weak.
- Prioritise queries that discriminate the hull: structures predicted near or
  below the hull with high uncertainty, and compositions with no measurements.
- If a calculation failed and has not been resolved, decide whether to RETRY
  it or ABANDON it. A run that already failed once as a retry should be abandoned.
- Propose at most 3 structure labels per decision (action_type
  RUN_STRUCTURE_ENERGY), chosen from the unmeasured pool.
- If the budget is exhausted, or the predicted stable set is confidently
  resolved, FINISH the campaign and say why.
- Fill hypothesis / evidence / uncertainty / expected_information_gain with
  concise, concrete scientific statements grounded in the numbers you saw.
"""


class AlloyMeasurement(BaseModel):
    calculation_id: str
    label: str
    x: float
    energy_per_site: float
    e_form: float | None = None


class PoolPrediction(BaseModel):
    label: str
    x: float
    e_form_mean: float | None = None
    e_form_std: float | None = None
    measured: bool = False
    predicted_stable: bool = False


class AlloyState(BaseScientificState):
    composition_min: float
    composition_max: float
    n_structures: int
    endpoints_measured: bool
    pure_a_label: str
    pure_b_label: str
    measurements: list[AlloyMeasurement] = Field(default_factory=list)
    pool_predictions: list[PoolPrediction] = Field(default_factory=list)
    predicted_stable: list[str] = Field(default_factory=list)
    unmeasured_labels: list[str] = Field(default_factory=list)
    suggested_uncertainty_label: str | None = None
    suggested_coverage_label: str | None = None


def _structure_from_row(row: Structure) -> AlloyStructure:
    return AlloyStructure(
        label=row.label,
        occupations=tuple(tuple(int(v) for v in r) for r in row.occupations),
        shape=(int(row.shape[0]), int(row.shape[1])),
        x=float(row.composition),
        n_sites=int(row.n_sites),
        features=tuple(float(f) for f in row.features),
    )


async def _load_pool(session: AsyncSession, campaign_id: str) -> list[Structure]:
    return (
        (
            await session.execute(
                select(Structure)
                .where(Structure.campaign_id == campaign_id)
                .order_by(Structure.label)
            )
        )
        .scalars()
        .all()
    )


def _measured_energies(calcs: list[Calculation]) -> dict[str, tuple[str, float]]:
    """structure_id -> (calculation_id, energy_per_site) from succeeded queries."""
    out: dict[str, tuple[str, float]] = {}
    for c in calcs:
        if (
            c.calculation_type == "STRUCTURE_ENERGY"
            and c.status == "SUCCEEDED"
            and c.output
            and c.structure_id
        ):
            out[c.structure_id] = (c.id, float(c.output["energy_per_site"]))
    return out


async def build_alloy_state(session: AsyncSession, campaign: Campaign) -> AlloyState:
    rows = await _load_pool(session, campaign.id)
    calcs = await load_campaign_calculations(session, campaign.id)
    measured = _measured_energies(calcs)
    by_id = {r.id: r for r in rows}

    # Endpoints may be absent before the pool is enumerated (campaign not yet
    # started); the hull view polls this before start, so degrade gracefully.
    pure_a = next((r for r in rows if r.composition == 0.0), None)
    pure_b = next((r for r in rows if r.composition == 1.0), None)
    e_a = measured[pure_a.id][1] if pure_a is not None and pure_a.id in measured else None
    e_b = measured[pure_b.id][1] if pure_b is not None and pure_b.id in measured else None
    endpoints_measured = e_a is not None and e_b is not None

    measurements = []
    for sid, (calc_id, e_site) in measured.items():
        row = by_id[sid]
        e_form = None
        if endpoints_measured:
            e_form = e_site - (1 - row.composition) * e_a - row.composition * e_b
        measurements.append(
            AlloyMeasurement(
                calculation_id=calc_id,
                label=row.label,
                x=row.composition,
                energy_per_site=e_site,
                e_form=e_form,
            )
        )
    measurements.sort(key=lambda m: (m.x, m.label))

    latest = await latest_surrogate_model(session, campaign.id)
    latest_model = None
    predictions: list[PoolPrediction] = []
    predicted_stable: list[str] = []
    if latest is not None:
        metrics = latest.validation_metrics
        loocv = metrics.get("loocv_rmse")
        loocv_text = f"{loocv:.4f}" if loocv is not None else "n/a"
        latest_model = ModelSummary(
            version=latest.version,
            n_training_points=metrics.get("n_training_points", 0),
            uncertainty_metric=metrics.get("stable_uncertainty"),
            summary_text=(
                f"CE v{latest.version}: LOOCV RMSE {loocv_text}, "
                f"{len(latest.artifact.get('stable_labels', []))} predicted stable phases"
            ),
        )
        art = latest.artifact
        predicted_stable = list(art.get("stable_labels", []))
        stable_set = set(predicted_stable)
        measured_labels = {by_id[sid].label for sid in measured}
        for label, x, mean, std in zip(
            art["labels"], art["x"], art["e_form_mean"], art["e_form_std"]
        ):
            predictions.append(
                PoolPrediction(
                    label=label,
                    x=x,
                    e_form_mean=mean,
                    e_form_std=std,
                    measured=label in measured_labels,
                    predicted_stable=label in stable_set,
                )
            )
    else:
        measured_labels = {by_id[sid].label for sid in measured}
        predictions = [
            PoolPrediction(label=r.label, x=r.composition, measured=r.label in measured_labels)
            for r in rows
        ]

    unmeasured = [p.label for p in predictions if not p.measured]

    # Suggestions for the baseline strategies (and as validation fallbacks).
    suggested_uncertainty = None
    candidates = [p for p in predictions if not p.measured and p.e_form_std is not None]
    if candidates:
        suggested_uncertainty = max(candidates, key=lambda p: p.e_form_std).label
    suggested_coverage = None
    if unmeasured:
        measured_x = [m.x for m in measurements] or [0.5]
        by_label = {p.label: p for p in predictions}
        suggested_coverage = max(
            unmeasured,
            key=lambda lab: min(abs(by_label[lab].x - mx) for mx in measured_x),
        )

    used = budget_used(calcs)
    return AlloyState(
        campaign_id=campaign.id,
        objective=campaign.objective,
        strategy=campaign.strategy,
        budget_total=campaign.simulation_budget,
        budget_used=used,
        budget_remaining=max(campaign.simulation_budget - used, 0),
        target_uncertainty=campaign.target_uncertainty,
        unresolved_failures=unresolved_failures(
            calcs,
            lambda c: f"structure {c.input_parameters.get('structure_label', '?')}",
        ),
        latest_model=latest_model,
        composition_min=campaign.composition_min if campaign.composition_min is not None else 0.0,
        composition_max=campaign.composition_max if campaign.composition_max is not None else 1.0,
        n_structures=len(rows),
        endpoints_measured=endpoints_measured,
        pure_a_label=pure_a.label if pure_a is not None else "",
        pure_b_label=pure_b.label if pure_b is not None else "",
        measurements=measurements,
        pool_predictions=predictions,
        predicted_stable=predicted_stable,
        unmeasured_labels=unmeasured,
        suggested_uncertainty_label=suggested_uncertainty,
        suggested_coverage_label=suggested_coverage,
    )


def _endpoint_decision(state: AlloyState) -> ScientificDecision:
    labels = [
        lab
        for lab in (state.pure_a_label, state.pure_b_label)
        if lab in state.unmeasured_labels
    ]
    return ScientificDecision(
        hypothesis="Formation energies require the pure-element reference energies; "
        "measure both endpoints first.",
        evidence=["E_form(x) = E(x) - (1-x)E(A) - xE(B)"],
        uncertainty="Without references, no formation energy or hull can be constructed.",
        action_type=ActionType.RUN_STRUCTURE_ENERGY,
        structure_labels=labels,
        expected_information_gain="Anchors the entire formation-energy scale.",
    )


class AlloyHeuristicDecider:
    """Baselines: random / composition-coverage ('grid') / uncertainty sampling."""

    def __init__(
        self,
        strategy_name: str,
        seed: int = 0,
        retry_adjustment: dict | None = None,
        retry_reason: str | None = None,
    ):
        self.name = strategy_name
        self._rng = np.random.default_rng(seed)
        self._retry_adjustment = (
            retry_adjustment if retry_adjustment is not None else ALLOY_RETRY_ADJUSTMENT
        )
        self._retry_reason = retry_reason or ALLOY_RETRY_REASON

    async def decide(self, state: AlloyState) -> ScientificDecision:
        # Budget is a hard ceiling: stopping outranks even failure recovery.
        decision = check_stopping(state) or handle_failures(
            state, self._retry_adjustment, self._retry_reason
        )
        if decision is not None:
            return decision
        if not state.endpoints_measured:
            return _endpoint_decision(state)
        if not state.unmeasured_labels:
            return ScientificDecision(
                hypothesis="Every enumerated structure has been measured.",
                evidence=[f"{len(state.measurements)} measurements over the full pool"],
                uncertainty=model_summary_text(state),
                action_type=ActionType.FINISH_CAMPAIGN,
                stopping_rationale="Structure pool exhausted; the hull is fully measured.",
            )

        if self.name == "random":
            label = str(self._rng.choice(state.unmeasured_labels))
            rationale = "Baseline: uniformly random structure selection."
        elif self.name == "grid":
            label = state.suggested_coverage_label or str(
                self._rng.choice(state.unmeasured_labels)
            )
            rationale = "Baseline: cover the least-sampled composition region."
        else:  # uncertainty
            label = (
                state.suggested_uncertainty_label
                or state.suggested_coverage_label
                or str(self._rng.choice(state.unmeasured_labels))
            )
            rationale = "Query the structure with maximal cluster-expansion ensemble disagreement."

        by_label = {p.label: p for p in state.pool_predictions}
        x = by_label[label].x if label in by_label else float("nan")
        return ScientificDecision(
            hypothesis=f"Measuring structure {label} (x={x:.3f}) best refines the hull. "
            + rationale,
            evidence=[
                f"{len(state.measurements)} measured of {state.n_structures} structures",
                model_summary_text(state),
            ],
            uncertainty=model_summary_text(state),
            action_type=ActionType.RUN_STRUCTURE_ENERGY,
            structure_labels=[label],
            expected_information_gain=rationale,
        )


class AlloyLLMDecider:
    """Endpoint bootstrap in code; everything else delegated to the LLM scientist."""

    name = "agent"

    def __init__(self, instructions: str = ALLOY_LLM_INSTRUCTIONS):
        from ..agent.llm import LLMDecider

        self._llm = LLMDecider(
            instructions=instructions,
            render_state=render_alloy_state,
            action_types=(ActionType.RUN_STRUCTURE_ENERGY,),
        )
        self.last_usage = None

    async def decide(self, state: AlloyState) -> ScientificDecision:
        if not state.endpoints_measured and not state.unresolved_failures:
            return _endpoint_decision(state)
        decision = await self._llm.decide(state)
        self.last_usage = self._llm.last_usage
        return decision


def render_alloy_state(state: AlloyState) -> str:
    by_label = {p.label: p for p in state.pool_predictions}
    top_uncertain = sorted(
        (p for p in state.pool_predictions if not p.measured and p.e_form_std is not None),
        key=lambda p: -(p.e_form_std or 0.0),
    )[:15]
    payload = {
        "objective": state.objective,
        "composition_range": [state.composition_min, state.composition_max],
        "budget": {
            "total": state.budget_total,
            "used": state.budget_used,
            "remaining": state.budget_remaining,
        },
        "pool_size": state.n_structures,
        "measurements": [
            {
                "label": m.label,
                "x": round(m.x, 4),
                "e_per_site": round(m.energy_per_site, 4),
                "e_form": round(m.e_form, 4) if m.e_form is not None else None,
            }
            for m in state.measurements
        ],
        "predicted_stable_structures": [
            {
                "label": lab,
                "x": round(by_label[lab].x, 4) if lab in by_label else None,
                "e_form": by_label[lab].e_form_mean if lab in by_label else None,
                "measured": by_label[lab].measured if lab in by_label else None,
            }
            for lab in state.predicted_stable
        ],
        "most_uncertain_unmeasured": [
            {
                "label": p.label,
                "x": round(p.x, 4),
                "e_form_pred": round(p.e_form_mean, 4) if p.e_form_mean is not None else None,
                "e_form_std": round(p.e_form_std, 4) if p.e_form_std is not None else None,
            }
            for p in top_uncertain
        ],
        "unresolved_failures": [f.model_dump() for f in state.unresolved_failures],
        "latest_cluster_expansion": (
            state.latest_model.model_dump() if state.latest_model else None
        ),
        "n_unmeasured": len(state.unmeasured_labels),
    }
    return (
        "Current scientific state (all numbers computed by deterministic tools). "
        "Use the get_pool_predictions tool for the full structure table.\n"
        + json.dumps(payload, indent=2)
        + "\nDecide the next action."
    )


class AlloyProblem:
    problem_type = "alloy_v1"
    llm_instructions = ALLOY_LLM_INSTRUCTIONS

    def pool_item(self, row: Structure):
        """Row -> object exposing .label / .x / .feature_vector() for the CE machinery."""
        return _structure_from_row(row)

    async def initialize(self, session: AsyncSession, campaign: Campaign) -> None:
        existing = await _load_pool(session, campaign.id)
        if existing:
            return
        x_min = campaign.composition_min if campaign.composition_min is not None else 0.0
        x_max = campaign.composition_max if campaign.composition_max is not None else 1.0
        pool = enumerate_structures(x_min=x_min, x_max=x_max)
        for s in pool:
            n_b = round(s.x * s.n_sites)
            session.add(
                Structure(
                    campaign_id=campaign.id,
                    label=s.label,
                    chemical_formula=f"A{s.n_sites - n_b}B{n_b}",
                    composition=s.x,
                    n_sites=s.n_sites,
                    occupations=[list(r) for r in s.occupations],
                    shape=list(s.shape),
                    features=list(s.features),
                )
            )
        await session.commit()
        await emit_agent_event(
            session,
            campaign.id,
            "POOL_ENUMERATED",
            action=f"Enumerated {len(pool)} correlation-distinct candidate structures "
            f"in x ∈ [{x_min:.2f}, {x_max:.2f}] (endpoints included as references)",
            payload={"n_structures": len(pool)},
        )

    async def build_state(self, session: AsyncSession, campaign: Campaign) -> AlloyState:
        return await build_alloy_state(session, campaign)

    def instructions_for(self, campaign: Campaign) -> str:
        """LLM instructions with the campaign's element pair substituted."""
        pair = "-".join((campaign.problem_config or {}).get("elements", campaign.elements or ["A", "B"]))
        return self.llm_instructions.replace("{elements}", pair)

    def decider(self, campaign: Campaign) -> Decider:
        if campaign.strategy == "agent":
            return AlloyLLMDecider(instructions=self.instructions_for(campaign))
        return AlloyHeuristicDecider(campaign.strategy, seed=stable_seed(campaign.id))

    def validate(self, state: AlloyState, decision: ScientificDecision) -> ScientificDecision:
        if decision.action_type == ActionType.RUN_STRUCTURE_ENERGY:
            valid = set(state.unmeasured_labels)
            cleaned: list[str] = []
            for label in decision.structure_labels:
                if label in valid and label not in cleaned:
                    cleaned.append(label)
            limit = min(MAX_TARGETS_PER_DECISION, state.budget_remaining)
            cleaned = cleaned[:limit]
            if not cleaned:
                fallback = (
                    state.suggested_uncertainty_label
                    or state.suggested_coverage_label
                    or (state.unmeasured_labels[0] if state.unmeasured_labels else None)
                )
                if fallback is None:
                    raise ValueError("no unmeasured structures remain to run")
                cleaned = [fallback]
            decision = decision.model_copy(update={"structure_labels": cleaned})
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
        rows = await _load_pool(session, campaign.id)
        by_label = {r.label: r for r in rows}
        calcs = await load_campaign_calculations(session, campaign.id)
        n_existing = len(calcs)
        created: list[Calculation] = []
        for i, label in enumerate(decision.structure_labels):
            row = by_label[label]
            calc = Calculation(
                campaign_id=campaign.id,
                structure_id=row.id,
                calculation_type="STRUCTURE_ENERGY",
                engine="alloyscience.alloy.StructureOracle",
                input_parameters={
                    "structure_label": row.label,
                    "composition": row.composition,
                    "occupations": row.occupations,
                    "shape": row.shape,
                    "features": row.features,
                    "n_sites": row.n_sites,
                    "seed": n_existing + i,
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
        rows = await _load_pool(session, campaign.id)
        calcs = await load_campaign_calculations(session, campaign.id)
        measured = _measured_energies(calcs)
        if len(measured) < ClusterExpansionSurrogate.MIN_POINTS:
            return
        pure = [r for r in rows if r.composition in (0.0, 1.0)]
        if not all(r.id in measured for r in pure):
            return

        training_ids = sorted(calc_id for calc_id, _ in measured.values())
        latest = await latest_surrogate_model(session, campaign.id)
        if latest is not None and latest.training_calculation_ids == training_ids:
            return

        pool = [self.pool_item(r) for r in rows]
        index_by_id = {r.id: i for i, r in enumerate(rows)}
        acq = AlloyAcquisitionState(pool=pool)
        for sid, (_, e_site) in measured.items():
            acq.measured_energies[index_by_id[sid]] = e_site

        seed = stable_seed(campaign.id)

        def _fit():
            surrogate = acq.surrogate(seed=seed)
            e_form, stable, hull_x, hull_e, e_form_std = predicted_hull_from_state(
                acq, seed=seed
            )
            loocv = surrogate.loocv_rmse() if surrogate else float("nan")
            coefficients = surrogate.coefficient_summary() if surrogate else {}
            return e_form, stable, hull_x, hull_e, e_form_std, loocv, coefficients

        e_form, stable, hull_x, hull_e, e_form_std, loocv, coefficients = (
            await asyncio.to_thread(_fit)
        )
        stable_uncertainty = max((e_form_std[lab] for lab in stable), default=0.0)
        model = SurrogateModel(
            campaign_id=campaign.id,
            type="cluster_expansion",
            version=(latest.version + 1) if latest else 1,
            training_calculation_ids=training_ids,
            parameters={"features": ["1", "point", "nn", "nnn"], "n_ensemble": 50},
            validation_metrics={
                "loocv_rmse": None if np.isnan(loocv) else loocv,
                "stable_uncertainty": stable_uncertainty,
                "n_training_points": len(training_ids),
                "coefficients": coefficients,
            },
            artifact={
                "labels": [s.label for s in pool],
                "x": [s.x for s in pool],
                "e_form_mean": [e_form[s.label] for s in pool],
                "e_form_std": [e_form_std[s.label] for s in pool],
                "measured": [index_by_id[r.id] in acq.measured_energies for r in rows],
                "stable_labels": stable,
                "hull_x": hull_x,
                "hull_e": hull_e,
            },
        )
        session.add(model)
        await session.commit()
        loocv_text = "n/a" if np.isnan(loocv) else f"{loocv:.4f}"
        await emit_agent_event(
            session,
            campaign.id,
            "MODEL_UPDATED",
            agent_run_id=agent_run_id,
            action=(
                f"Cluster expansion v{model.version} fitted on {len(training_ids)} energies: "
                f"LOOCV RMSE {loocv_text}, {len(stable)} predicted stable structures, "
                f"max stable-phase uncertainty {stable_uncertainty:.4f}"
            ),
            tool_output_reference=f"surrogate_model:{model.id}",
            payload={
                "version": model.version,
                "loocv_rmse": model.validation_metrics["loocv_rmse"],
                "n_stable": len(stable),
                "stable_labels": stable,
            },
        )

    def describe_action(self, decision: ScientificDecision) -> str:
        if decision.action_type == ActionType.RUN_STRUCTURE_ENERGY:
            labels = ", ".join(decision.structure_labels)
            return f"Query oracle energies for structures: {labels}"
        return _generic_action_text(decision)
