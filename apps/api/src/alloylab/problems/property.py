"""Property-search problem adapter (Milestone 8, plan section 22 V3):

    maximise bulk modulus subject to (i) thermodynamic stability (on the
    0 K hull) and (ii) remaining ORDERED below a threshold temperature.

Two surrogates over the same cluster vectors (energy -> hull, bulk modulus),
plus Milestone 5's canonical MC used as a verification tool: the agent spends
budget to run MC at the threshold temperature ON ITS OWN FITTED CE and checks
the Warren-Cowley order parameter. Candidates are ranked per plan section 14.
"""

from __future__ import annotations

import asyncio
import json

import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.benchmark import AlloyAcquisitionState, predicted_hull_from_state
from alloyscience.property.benchmark import (
    fit_property_surrogate,
    predicted_candidates,
    property_pool,
    propose_property_query,
)

from ..agent.decisions import ActionType, ScientificDecision
from ..agent.state import latest_surrogate_model, load_campaign_calculations
from ..agent.strategies import (
    Decider,
    check_stopping,
    handle_failures,
    model_summary_text,
    stable_seed,
)
from ..db.models import Calculation, Campaign, Structure, SurrogateModel
from ..events import emit_agent_event
from .alloy import (
    ALLOY_RETRY_ADJUSTMENT,
    ALLOY_RETRY_REASON,
    AlloyProblem,
    AlloyState,
    _endpoint_decision,
    _load_pool,
    _measured_energies,
    build_alloy_state,
)
from .fcc import _CvPoolItem
from .ising import _generic_action_text

ORDERED_SRO_THRESHOLD = -0.15
VERIFICATION_TRIAL_STEPS = 20_000

PROPERTY_LLM_INSTRUCTIONS = """\
You are an autonomous computational materials scientist searching FCC {elements}
orderings for the STIFFEST alloy that is (i) thermodynamically stable (on the
0 K formation-energy hull) and (ii) stays ORDERED below a threshold
temperature. Each structure query returns energy and bulk modulus (expensive);
you may also spend budget on a canonical Monte Carlo verification at the
threshold temperature on the fitted cluster expansion (action RUN_MONTE_CARLO
with `composition` set to a measured candidate's composition), which reports
whether the ordering survives (Warren-Cowley SRO < -0.15 = ordered).

Rules:
- You never compute physical quantities yourself; every number you cite must
  come from the provided state.
- Early on, discriminate the hull; then concentrate on high-bulk-modulus
  candidates near the hull; verify the top measured candidates' finite-T
  stability before finishing. Never recommend an unmeasured structure.
- Propose at most 3 structure labels per RUN_STRUCTURE_ENERGY decision.
- If a calculation failed and is unresolved, RETRY or ABANDON it.
- FINISH when the budget is exhausted or the best stable, verified candidate
  is confidently identified; state the recommendation in stopping_rationale.
"""


class CandidateSummary(BaseModel):
    label: str
    x: float
    e_form: float
    e_form_std: float
    e_above_hull: float
    bulk_modulus: float
    bulk_modulus_std: float
    measured: bool
    stable_0k: bool
    stability_at_threshold: str
    score: float


class PropertyState(AlloyState):
    temperature_threshold: float
    bulk_by_label: dict[str, float] = Field(default_factory=dict)
    candidates: list[CandidateSummary] = Field(default_factory=list)
    verification_by_x: dict[str, str] = Field(default_factory=dict)  # str(x) -> verdict
    suggested_property_label: str | None = None
    suggested_verification_x: float | None = None
    top_candidate_label: str | None = None


def _bulk_measurements(calcs: list[Calculation]) -> dict[str, float]:
    out: dict[str, float] = {}
    for c in calcs:
        if c.calculation_type == "STRUCTURE_ENERGY" and c.status == "SUCCEEDED" and c.output:
            b = c.output.get("bulk_modulus_gpa")
            if b is not None and c.structure_id:
                out[c.structure_id] = float(b)
    return out


def _verifications(calcs: list[Calculation]) -> dict[float, str]:
    out: dict[float, str] = {}
    for c in calcs:
        if c.calculation_type == "MONTE_CARLO" and c.status == "SUCCEEDED" and c.output:
            x = round(float(c.input_parameters.get("composition", -1)), 6)
            sro = float(c.output.get("sro", 0.0))
            out[x] = "ordered" if sro < ORDERED_SRO_THRESHOLD else "disordered"
    return out


def _acquisition(rows: list[Structure], measured: dict, bulk: dict):
    pool = [_CvPoolItem(r.label, float(r.composition), tuple(float(f) for f in r.features)) for r in rows]
    index_by_id = {r.id: i for i, r in enumerate(rows)}
    acq = AlloyAcquisitionState(pool=pool)
    for sid, (_, e) in measured.items():
        acq.measured_energies[index_by_id[sid]] = e
    bulk_by_index = {index_by_id[sid]: b for sid, b in bulk.items() if sid in index_by_id}
    return acq, bulk_by_index


async def build_property_state(session: AsyncSession, campaign: Campaign) -> PropertyState:
    base = await build_alloy_state(session, campaign)
    rows = await _load_pool(session, campaign.id)
    calcs = await load_campaign_calculations(session, campaign.id)
    measured = _measured_energies(calcs)
    bulk = _bulk_measurements(calcs)
    by_id = {r.id: r for r in rows}
    verification = _verifications(calcs)
    t_thr = float((campaign.problem_config or {}).get("t_threshold", 1200.0))

    candidates: list[CandidateSummary] = []
    latest = await latest_surrogate_model(session, campaign.id)
    if latest is not None:
        for c in latest.artifact.get("candidates", []):
            candidates.append(CandidateSummary(**c))
        # Refresh verdicts (verification may have landed after the last fit).
        for c in candidates:
            if c.x not in (0.0, 1.0):
                c.stability_at_threshold = verification.get(round(c.x, 6), "unverified")
                if c.stability_at_threshold == "disordered" and c.score > -1e5:
                    c.score -= 1e6
        candidates.sort(key=lambda c: (-c.score, c.e_form))

    suggested_property = None
    if base.endpoints_measured and len(measured) >= 4:
        acq, bulk_by_index = _acquisition(rows, measured, bulk)
        try:
            i = propose_property_query(acq, bulk_by_index, "property", np.random.default_rng(stable_seed(campaign.id)))
            suggested_property = acq.pool[i].label
        except ValueError:
            suggested_property = None

    measured_labels = {by_id[sid].label for sid in measured}
    verify_x = None
    for c in candidates:
        if (
            c.measured and c.stable_0k and c.x not in (0.0, 1.0)
            and c.stability_at_threshold == "unverified" and c.label in measured_labels
        ):
            verify_x = c.x
            break

    top = next((c.label for c in candidates if c.measured and c.stable_0k and c.x not in (0.0, 1.0)
                and c.stability_at_threshold != "disordered"), None)

    return PropertyState(
        **base.model_dump(),
        temperature_threshold=t_thr,
        bulk_by_label={by_id[sid].label: b for sid, b in bulk.items()},
        candidates=candidates,
        verification_by_x={str(k): v for k, v in verification.items()},
        suggested_property_label=suggested_property,
        suggested_verification_x=verify_x,
        top_candidate_label=top,
    )


def _verification_decision(state: PropertyState, x: float) -> ScientificDecision:
    cand = next((c for c in state.candidates if c.x == x and c.measured), None)
    return ScientificDecision(
        hypothesis=(
            f"Candidate {cand.label if cand else '?'} (x={x:.3f}, B≈{cand.bulk_modulus:.0f} GPa) "
            f"is predicted stable at 0 K; verify it stays ordered at {state.temperature_threshold:.0f} K."
        ),
        evidence=[model_summary_text(state), "verification via canonical MC on the fitted CE"],
        uncertainty="Finite-temperature order is not implied by 0 K stability.",
        action_type=ActionType.RUN_MONTE_CARLO,
        composition=x,
        temperatures=[state.temperature_threshold],
        expected_information_gain="Resolves the temperature constraint for the top candidate.",
    )


class PropertyHeuristicDecider:
    """random / composition coverage ('grid') / property-directed ('uncertainty')."""

    def __init__(self, strategy_name: str, seed: int = 0):
        self.name = strategy_name
        self._rng = np.random.default_rng(seed)

    async def decide(self, state: PropertyState) -> ScientificDecision:
        decision = check_stopping(state) or handle_failures(state, ALLOY_RETRY_ADJUSTMENT, ALLOY_RETRY_REASON)
        if decision is not None:
            return decision
        if not state.endpoints_measured:
            return _endpoint_decision(state)
        # Reserve the tail of the budget for finite-temperature verification.
        verification_phase = state.budget_used >= max(6, int(0.7 * state.budget_total))
        if verification_phase and state.suggested_verification_x is not None:
            return _verification_decision(state, state.suggested_verification_x)
        if not state.unmeasured_labels:
            return ScientificDecision(
                hypothesis="Every structure is measured.", evidence=[], uncertainty=model_summary_text(state),
                action_type=ActionType.FINISH_CAMPAIGN, stopping_rationale="Pool exhausted.",
            )
        if self.name == "random":
            label = str(self._rng.choice(state.unmeasured_labels)); why = "Baseline: random structure."
        elif self.name == "grid":
            label = state.suggested_coverage_label or str(self._rng.choice(state.unmeasured_labels))
            why = "Baseline: cover the least-sampled composition."
        else:
            label = state.suggested_property_label or state.suggested_uncertainty_label or str(self._rng.choice(state.unmeasured_labels))
            why = "Property-directed: highest predicted bulk modulus among near-hull candidates, weighted by hull uncertainty."
        return ScientificDecision(
            hypothesis=f"Measuring {label} best advances the stiff-and-stable search. {why}",
            evidence=[f"{len(state.measurements)} measured of {state.n_structures}", model_summary_text(state)],
            uncertainty=model_summary_text(state),
            action_type=ActionType.RUN_STRUCTURE_ENERGY, structure_labels=[label],
            expected_information_gain=why,
        )


class PropertyLLMDecider:
    name = "agent"

    def __init__(self, instructions: str = PROPERTY_LLM_INSTRUCTIONS):
        from ..agent.llm import LLMDecider

        self._llm = LLMDecider(
            instructions=instructions, render_state=render_property_state,
            action_types=(ActionType.RUN_STRUCTURE_ENERGY, ActionType.RUN_MONTE_CARLO),
        )
        self.last_usage = None

    async def decide(self, state: PropertyState) -> ScientificDecision:
        if not state.endpoints_measured and not state.unresolved_failures:
            return _endpoint_decision(state)
        decision = await self._llm.decide(state)
        self.last_usage = self._llm.last_usage
        return decision


def render_property_state(state: PropertyState) -> str:
    payload = {
        "objective": state.objective,
        "temperature_threshold_K": state.temperature_threshold,
        "budget": {"total": state.budget_total, "used": state.budget_used, "remaining": state.budget_remaining},
        "measured": [
            {"label": m.label, "x": round(m.x, 3), "e_form": round(m.e_form, 4) if m.e_form is not None else None,
             "B_GPa": round(state.bulk_by_label[m.label], 1) if m.label in state.bulk_by_label else None}
            for m in state.measurements
        ],
        "top_candidates": [
            {"label": c.label, "x": round(c.x, 3), "e_form": round(c.e_form, 4), "e_above_hull": round(c.e_above_hull, 4),
             "B_GPa": round(c.bulk_modulus, 1), "B_std": round(c.bulk_modulus_std, 1), "measured": c.measured,
             "stable_0K": c.stable_0k, "at_threshold": c.stability_at_threshold}
            for c in state.candidates[:12]
        ],
        "verifications": state.verification_by_x,
        "unresolved_failures": [f.model_dump() for f in state.unresolved_failures],
        "latest_model": state.latest_model.model_dump() if state.latest_model else None,
        "n_unmeasured": len(state.unmeasured_labels),
    }
    return "Current scientific state:\n" + json.dumps(payload, indent=2) + "\nDecide the next action."


class PropertyProblem(AlloyProblem):
    problem_type = "property_v3"
    llm_instructions = PROPERTY_LLM_INSTRUCTIONS

    def pool_item(self, row: Structure) -> _CvPoolItem:
        return _CvPoolItem(row.label, float(row.composition), tuple(float(f) for f in row.features))

    async def initialize(self, session: AsyncSession, campaign: Campaign) -> None:
        if await _load_pool(session, campaign.id):
            return
        cfg = campaign.problem_config or {}
        max_size = int(cfg.get("max_size", 5))
        elements = tuple(cfg.get("elements", ["Ni", "Al"]))
        system, pool = property_pool(max_size, float(cfg.get("a_parent", 3.52)), elements)
        for s in pool:
            session.add(Structure(
                campaign_id=campaign.id, label=s.label, chemical_formula=s.chemical_formula,
                composition=s.x, n_sites=s.n_sites, occupations=[], shape=[],
                features=list(s.cluster_vector), lattice=[list(r) for r in s.cell],
                positions=[list(p) for p in s.positions], atomic_numbers=list(s.atomic_numbers),
            ))
        await session.commit()
        t_thr = (campaign.problem_config or {}).get("t_threshold", 1200.0)
        engine = (campaign.problem_config or {}).get("engine", "hidden")
        await emit_agent_event(
            session, campaign.id, "POOL_ENUMERATED",
            action=f"Enumerated {len(pool)} FCC {elements[0]}-{elements[1]} orderings ({system.n_parameters}-parameter cluster space); "
                   f"objective: max bulk modulus, stable at 0 K and ordered below {t_thr:.0f} K; "
                   f"energy/property engine: {engine}",
            payload={"n_structures": len(pool), "t_threshold": t_thr, "engine": engine},
        )

    async def build_state(self, session: AsyncSession, campaign: Campaign) -> PropertyState:
        return await build_property_state(session, campaign)

    def decider(self, campaign: Campaign) -> Decider:
        if campaign.strategy == "agent":
            return PropertyLLMDecider(instructions=self.instructions_for(campaign))
        return PropertyHeuristicDecider(campaign.strategy, seed=stable_seed(campaign.id))

    def validate(self, state: PropertyState, decision: ScientificDecision) -> ScientificDecision:
        if decision.action_type == ActionType.RUN_MONTE_CARLO:
            xs = sorted({m.x for m in state.measurements if 0.0 < m.x < 1.0})
            if not xs:
                # Nothing measured to verify: fall back to a structure query.
                decision = decision.model_copy(update={"action_type": ActionType.RUN_STRUCTURE_ENERGY})
                return super().validate(state, decision)
            x = decision.composition if decision.composition is not None else (state.suggested_verification_x or xs[0])
            x = min(xs, key=lambda v: abs(v - float(x)))
            if state.budget_remaining <= 0:
                raise ValueError("no budget for verification")
            return decision.model_copy(update={"composition": x, "temperatures": [state.temperature_threshold]})
        return super().validate(state, decision)

    async def create_calculations(self, session: AsyncSession, campaign: Campaign, decision: ScientificDecision) -> list[str]:
        if decision.action_type == ActionType.RUN_STRUCTURE_ENERGY:
            ids = await super().create_calculations(session, campaign, decision)
            engine = (campaign.problem_config or {}).get("engine", "hidden")
            labels = {
                "emt": "ase.calculators.emt.EMT",
                "espresso": "quantum-espresso pw.x (E(V) scan)",
            }
            for cid in ids:
                calc = await session.get(Calculation, cid)
                calc.engine = labels.get(engine, "hidden CE + hidden bulk-modulus oracle")
                if engine == "espresso":
                    params = dict(calc.input_parameters)
                    espresso_cfg = (campaign.problem_config or {}).get("espresso", {})
                    params["electron_maxstep"] = int(espresso_cfg.get("electron_maxstep", 60))
                    params["mixing_beta"] = float(espresso_cfg.get("mixing_beta", 0.4))
                    calc.input_parameters = params
            await session.commit()
            return ids
        latest = await latest_surrogate_model(session, campaign.id)
        ecis = list((latest.artifact if latest else {}).get("ecis", []))
        if not ecis:
            raise ValueError("no fitted cluster expansion available for verification")
        n_existing = len(await load_campaign_calculations(session, campaign.id))
        calc = Calculation(
            campaign_id=campaign.id, calculation_type="MONTE_CARLO", engine="mchammer.CanonicalEnsemble (fitted CE)",
            input_parameters={
                "composition": float(decision.composition), "temperature": float(decision.temperatures[0]),
                "supercell_repeat": 4, "n_trial_steps": VERIFICATION_TRIAL_STEPS,
                "seed": stable_seed(campaign.id) % 100_000 + n_existing, "ecis": ecis,
                "failure_rate": campaign.failure_rate, "purpose": "finite_temperature_verification",
            },
        )
        session.add(calc)
        await session.flush()
        cid = calc.id
        await session.commit()
        return [cid]

    async def update_models(self, session: AsyncSession, campaign: Campaign, agent_run_id: str | None) -> None:
        rows = await _load_pool(session, campaign.id)
        calcs = await load_campaign_calculations(session, campaign.id)
        measured = _measured_energies(calcs)
        bulk = _bulk_measurements(calcs)
        if len(measured) < 4 or not all(r.id in measured for r in rows if r.composition in (0.0, 1.0)):
            return
        training_ids = sorted(cid for cid, _ in measured.values())
        verification = _verifications(calcs)
        latest = await latest_surrogate_model(session, campaign.id)
        signature = training_ids + [f"v:{k}:{v}" for k, v in sorted(verification.items())]
        if latest is not None and latest.training_calculation_ids == signature:
            return
        acq, bulk_by_index = _acquisition(rows, measured, bulk)
        seed = stable_seed(campaign.id)
        t_thr = float((campaign.problem_config or {}).get("t_threshold", 1200.0))

        def _fit():
            e_form, stable, hull_x, hull_e, e_form_std = predicted_hull_from_state(acq, seed=seed)
            candidates, stable_tol = predicted_candidates(acq, bulk_by_index, seed=seed, verification_by_x=verification)
            surrogate = acq.surrogate(seed=seed)
            b_surrogate = fit_property_surrogate(acq, bulk_by_index, seed=seed)
            return e_form, stable, hull_x, hull_e, e_form_std, candidates, stable_tol, surrogate, b_surrogate

        e_form, stable, hull_x, hull_e, e_form_std, candidates, stable_tol, surrogate, b_surrogate = await asyncio.to_thread(_fit)
        loocv = surrogate.loocv_rmse()
        b_loocv = b_surrogate.loocv_rmse() if b_surrogate else float("nan")
        pool = acq.pool
        top = next((c for c in candidates if c.measured and c.stable_0k and c.x not in (0.0, 1.0)
                    and c.stability_at_threshold != "disordered"), None)
        model = SurrogateModel(
            campaign_id=campaign.id, type="cluster_expansion+bulk_modulus",
            version=(latest.version + 1) if latest else 1, training_calculation_ids=signature,
            parameters={"features": "icet cluster vector (4.5 A pairs)", "t_threshold": t_thr},
            validation_metrics={
                "loocv_rmse": None if np.isnan(loocv) else float(loocv),
                "bulk_modulus_loocv_gpa": None if np.isnan(b_loocv) else float(b_loocv),
                "stable_uncertainty": max((e_form_std[lab] for lab in stable), default=0.0),
                "n_training_points": len(training_ids),
                "top_candidate_label": top.label if top else None,
                "top_candidate_bulk_modulus": top.bulk_modulus if top else None,
                "coefficients": surrogate.coefficient_summary(),
            },
            artifact={
                "labels": [s.label for s in pool], "x": [s.x for s in pool],
                "e_form_mean": [e_form[s.label] for s in pool], "e_form_std": [e_form_std[s.label] for s in pool],
                "measured": [i in acq.measured_energies for i in range(len(pool))],
                "stable_labels": stable, "hull_x": hull_x, "hull_e": hull_e,
                "candidates": [c.to_dict() for c in candidates],
                "ecis": [float(v) for v in surrogate.coefficients],
                "stable_tol": stable_tol,
            },
        )
        session.add(model)
        await session.commit()
        top_text = (f"top candidate {top.label} (x={top.x:.2f}, B={top.bulk_modulus:.0f} GPa, "
                    f"{top.stability_at_threshold} at {t_thr:.0f} K)") if top else "no stable intermetallic candidate yet"
        await emit_agent_event(
            session, campaign.id, "MODEL_UPDATED", agent_run_id=agent_run_id,
            action=f"Surrogates v{model.version}: CE LOOCV {loocv:.4f} eV, B LOOCV "
                   f"{'n/a' if np.isnan(b_loocv) else f'{b_loocv:.1f} GPa'}; {len(stable)} predicted stable; {top_text}",
            tool_output_reference=f"surrogate_model:{model.id}",
            payload={"version": model.version, "top_candidate": top.to_dict() if top else None},
        )

    async def finalize(self, session: AsyncSession, campaign: Campaign, agent_run_id: str | None) -> None:
        state = await build_property_state(session, campaign)
        top = next((c for c in state.candidates if c.label == state.top_candidate_label), None)
        if top is None:
            action = "No stable, ordered intermetallic candidate could be recommended within the budget."
        else:
            action = (
                f"RECOMMENDATION: {top.label} (x_Al={top.x:.3f}) — B = {top.bulk_modulus:.0f} GPa, "
                f"E_form = {top.e_form:.3f} eV/atom (stable at 0 K), "
                f"{top.stability_at_threshold} at {state.temperature_threshold:.0f} K"
            )
        await emit_agent_event(
            session, campaign.id, "FINAL_RECOMMENDATION", agent_run_id=agent_run_id, action=action,
            payload={"candidate": top.model_dump() if top else None, "temperature_threshold": state.temperature_threshold},
        )
        if top is not None:
            campaign.stopping_rationale = f"{campaign.stopping_rationale or ''} {action}".strip()
            await session.commit()

    def describe_action(self, decision: ScientificDecision) -> str:
        if decision.action_type == ActionType.RUN_MONTE_CARLO:
            return (f"Verify finite-T stability: canonical MC at x={decision.composition:.3f}, "
                    f"T={decision.temperatures[0]:.0f} K on the fitted CE")
        if decision.action_type == ActionType.RUN_STRUCTURE_ENERGY:
            return f"Query energy + bulk modulus for: {', '.join(decision.structure_labels)}"
        return _generic_action_text(decision)
