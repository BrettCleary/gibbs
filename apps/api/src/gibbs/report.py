"""Final scientific report (Milestone 9 "explain results", plan section 16).

Built deterministically from the campaign's persisted record — decisions,
calculations, models, failures, recommendation — so every number in it has
provenance. An optional LLM narrative pass may PARAPHRASE the structured
facts; it never introduces numbers of its own.
"""

from __future__ import annotations

import logging

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import AgentEvent, Calculation, Campaign, SurrogateModel

PROBLEM_TITLES = {
    "ising_v0": "2D Ising critical-region search",
    "alloy_v1": "Binary lattice-model ground-state search",
    "fcc_v2": "FCC {pair} hull discovery (hidden cluster expansion)",
    "phase_v2": "FCC {pair} order/disorder phase-boundary mapping",
    "dft_v3": "FCC {pair} hull discovery with a real energy engine",
    "property_v3": "Stiff-and-stable FCC {pair} intermetallic search",
}


async def build_report(session: AsyncSession, campaign: Campaign) -> dict:
    calcs = (
        (
            await session.execute(
                select(Calculation)
                .where(Calculation.campaign_id == campaign.id)
                .order_by(Calculation.created_at)
            )
        )
        .scalars()
        .all()
    )
    events = (
        (
            await session.execute(
                select(AgentEvent)
                .where(AgentEvent.campaign_id == campaign.id)
                .order_by(AgentEvent.created_at)
            )
        )
        .scalars()
        .all()
    )
    latest = (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign.id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    succeeded = [c for c in calcs if c.status == "SUCCEEDED"]
    failed = [c for c in calcs if c.status == "FAILED"]
    retries = [c for c in calcs if c.retry_of]
    by_type: dict[str, int] = {}
    for c in succeeded:
        by_type[c.calculation_type] = by_type.get(c.calculation_type, 0) + 1
    engines = sorted({c.engine for c in calcs})
    wall = sum(
        (c.completed_at - c.started_at).total_seconds()
        for c in calcs
        if c.completed_at and c.started_at
    )

    decisions = [e for e in events if e.event_type == "AGENT_DECISION"]
    failure_summary = {}
    for c in failed:
        failure_summary[c.failure_category or "UNKNOWN"] = (
            failure_summary.get(c.failure_category or "UNKNOWN", 0) + 1
        )
    recommendation = next(
        (e for e in reversed(events) if e.event_type == "FINAL_RECOMMENDATION"), None
    )

    metrics = dict(latest.validation_metrics) if latest else {}
    artifact = latest.artifact if latest else {}
    key_results = _key_results(campaign, metrics, artifact)

    limitations = _limitations(campaign, metrics, failed, retries, calcs)

    report = {
        "campaign_id": campaign.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": PROBLEM_TITLES.get(campaign.problem_type, campaign.problem_type).format(
            pair="-".join((campaign.problem_config or {}).get("elements", campaign.elements or ["Ni", "Al"]))
        ),
        "objective": campaign.objective,
        "status": campaign.status,
        "strategy": campaign.strategy,
        "problem_type": campaign.problem_type,
        "budget": {
            "total": campaign.simulation_budget,
            "used": campaign.simulations_used,
            "successful_by_type": by_type,
            "failed": len(failed),
            "retries": len(retries),
            "total_compute_seconds": round(wall, 1),
        },
        "engines": engines,
        "model": {
            "type": latest.type if latest else None,
            "version": latest.version if latest else None,
            "n_training_points": metrics.get("n_training_points"),
            "loocv_rmse": metrics.get("loocv_rmse"),
            "bulk_modulus_loocv_gpa": metrics.get("bulk_modulus_loocv_gpa"),
            "max_tc_std": metrics.get("max_tc_std"),
            "tc_mean": metrics.get("tc_mean"),
            "tc_std": metrics.get("tc_std"),
        },
        "key_results": key_results,
        "recommendation": {
            "text": recommendation.action if recommendation else None,
            "candidate": (recommendation.payload or {}).get("candidate") if recommendation else None,
        },
        "stopping_rationale": campaign.stopping_rationale,
        "failures": {"by_category": failure_summary, "n_retried": len(retries)},
        "decision_trail": [
            {
                "at": e.created_at.isoformat(),
                "hypothesis": e.hypothesis,
                "action": e.action,
                "evidence": e.reasoning_summary,
                # "code" for the coded baselines and the shared bootstrap/stopping/
                # failure policies, "llm" for model inference; absent on events
                # written before decisions recorded their provenance.
                "source": (e.payload or {}).get("source"),
            }
            for e in decisions
        ],
        "limitations": limitations,
        "narrative": None,
    }
    report["narrative"] = _deterministic_narrative(report)
    return report


def _key_results(campaign: Campaign, metrics: dict, artifact: dict) -> list[str]:
    out: list[str] = []
    pt = campaign.problem_type
    if pt == "ising_v0" and metrics.get("tc_mean") is not None:
        out.append(f"Critical temperature estimate Tc = {metrics['tc_mean']:.4f} ± {metrics['tc_std']:.4f}.")
    if pt in ("alloy_v1", "fcc_v2", "dft_v3", "property_v3"):
        stable = artifact.get("stable_labels", [])
        if stable:
            out.append(f"{len(stable)} structures predicted on/near the formation-energy hull: {', '.join(stable[:8])}{'…' if len(stable) > 8 else ''}.")
        if metrics.get("loocv_rmse") is not None:
            out.append(f"Cluster-expansion LOOCV RMSE {metrics['loocv_rmse']:.4f} eV/atom on {metrics.get('n_training_points')} measured energies.")
    if pt == "property_v3":
        top = metrics.get("top_candidate_label")
        if top:
            out.append(f"Top candidate {top}: predicted bulk modulus {metrics.get('top_candidate_bulk_modulus'):.0f} GPa.")
        cands = artifact.get("candidates", [])
        verified = [c for c in cands if c.get("stability_at_threshold") in ("ordered", "disordered")]
        if verified:
            n_ord = sum(1 for c in verified if c["stability_at_threshold"] == "ordered")
            out.append(f"Finite-temperature verification: {n_ord}/{len(verified)} verified compositions remain ordered at the threshold.")
    if pt == "phase_v2":
        for s in artifact.get("slices", []):
            if s.get("tc_mean") is not None:
                flag = " (window edge — bound, not location)" if s.get("tc_edge_pinned") else ""
                out.append(f"x = {s['x']:.2f}: Tc = {s['tc_mean']:.0f} ± {s['tc_std']:.0f} K{flag}.")
    return out


def _limitations(campaign: Campaign, metrics: dict, failed, retries, calcs) -> list[str]:
    out: list[str] = []
    cfg = campaign.problem_config or {}
    engine = cfg.get("engine")
    if engine == "espresso":
        n_vol = int((cfg.get("espresso") or {}).get("n_volumes", 1))
        geometry = (
            f"isotropic volume relaxation from a {n_vol}-point E(V) scan, no ionic relaxation"
            if n_vol > 1
            else "single-point energies at Vegard-scaled lattices (no relaxation)"
        )
        out.append(f"DFT settings are demo-grade: non-spin-polarised PBE, modest k-point mesh, {geometry}. Formation energies are qualitatively, not quantitatively, reliable.")
    if cfg.get("elements"):
        from alloyscience.calculators import element_info

        for sym in cfg["elements"]:
            try:
                info = element_info(sym)
            except ValueError:
                continue
            if not info.fcc_native:
                out.append(
                    f"{sym} is {info.structure.upper()} at ambient conditions; this campaign models a "
                    f"hypothetical FCC {'-'.join(cfg['elements'])} lattice (a = {info.a_fcc:.2f} Å, equal atomic volume), "
                    "not the real ground-state crystal structure."
                )
    if engine == "emt":
        pair = "-".join(cfg.get("elements", ["Ni", "Al"]))
        out.append(f"EMT is a classical effective-medium potential fitted to pure-element properties; its {pair} mixing energetics are only qualitative (for Ni-Al it predicts phase separation).")
    if cfg.get("hamiltonian") is not None and engine in (None, "hidden"):
        out.append("Energies come from a synthetic hidden Hamiltonian/cluster expansion; results validate the method, not real Ni-Al thermodynamics.")
    if metrics.get("loocv_rmse") is not None and metrics.get("n_training_points", 0) < 12:
        out.append(f"The surrogate is trained on only {metrics.get('n_training_points')} points; predictions for unmeasured structures carry the reported ensemble uncertainties and should be verified before use.")
    if failed:
        out.append(f"{len(failed)} calculation(s) failed ({len(retries)} retried); unresolved failures leave those structures unmeasured.")
    if campaign.problem_type == "property_v3":
        out.append("Finite-temperature verification uses the agent's fitted cluster expansion (not the reference engine) with a 64-atom canonical MC cell; the order/disorder verdict inherits the surrogate's error.")
    if campaign.status != "COMPLETED":
        out.append(f"Campaign status is {campaign.status}; results are provisional.")
    return out


def _deterministic_narrative(r: dict) -> str:
    b = r["budget"]
    parts = [
        f"{r['title']}. Objective: {r['objective']}",
        f"The campaign ran under the '{r['strategy']}' strategy and used {b['used']}/{b['total']} "
        f"of its simulation budget ({', '.join(f'{v} {k.lower().replace('_', ' ')}' for k, v in b['successful_by_type'].items()) or 'no successful runs'}; "
        f"{b['failed']} failed, {b['retries']} retried; {b['total_compute_seconds']:.0f} s of engine time) on {', '.join(r['engines']) or 'no engine'}.",
    ]
    if r["key_results"]:
        parts.append(" ".join(r["key_results"]))
    if r["recommendation"]["text"]:
        parts.append(r["recommendation"]["text"])
    if r["stopping_rationale"]:
        parts.append(f"Stopping rationale: {r['stopping_rationale']}")
    if r["limitations"]:
        parts.append("Limitations: " + " ".join(r["limitations"]))
    return "\n\n".join(parts)


async def llm_narrative(report: dict, model) -> str | None:
    """Optional prose pass (Pydantic AI). Numbers must come from the report.

    `model` is a provider-prefixed model string or a Pydantic AI Model instance;
    returns None when the provider's API key is not available.
    """
    import json

    from .agent.llm import model_available

    ok, _ = model_available(model)
    if not ok:
        return None
    from pydantic_ai import Agent

    agent = Agent(
        model,
        output_type=str,
        name="gibbs-reporter",
        instructions=(
            "You write the results section of a computational materials-science report. "
            "Use ONLY the numbers and facts in the provided structured report; do not invent "
            "values. Be concise, explicit about uncertainty and limitations, and state the "
            "recommendation plainly."
        ),
    )
    try:
        result = await agent.run(json.dumps(report, indent=2, default=str))
    except Exception:  # a dead key or provider outage must not sink the report
        logging.getLogger("gibbs.report").exception("LLM narrative failed; report keeps the deterministic narrative")
        return None
    return str(result.output)
