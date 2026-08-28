"""Derived campaign views shared by the REST endpoints and the copilot's tools.

Everything the dashboards draw — hull, phase diagram, ranked candidates — is
built here from persisted calculations and models, so the copilot "sees"
exactly what the scientist sees, never a separate summary.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models import Campaign, Structure, SurrogateModel
from .schemas import (
    AlloyHullView,
    CandidateRead,
    CandidatesView,
    HullPoint,
    PhaseDiagramView,
    PhaseMeasurementView,
    PhaseSliceView,
)

HULL_PROBLEMS = ("alloy_v1", "fcc_v2", "dft_v3", "property_v3")


def energy_unit(campaign: Campaign) -> str:
    """Unit of the hull energies: real engines report eV/atom; the hidden
    synthetic Hamiltonians (alloy_v1, fcc_v2, property_v3 'hidden') are
    dimensionless model energies."""
    if campaign.engine in ("emt", "espresso"):
        return "eV/atom"
    return "arb. units (hidden Hamiltonian)"


class ViewNotApplicable(ValueError):
    """The requested view does not exist for this campaign's problem type."""


async def latest_model(session: AsyncSession, campaign_id: str) -> SurrogateModel | None:
    return (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign_id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def hull_view(session: AsyncSession, campaign: Campaign) -> AlloyHullView:
    """Formation-energy hull view for alloy campaigns: measurements, predictions, hull."""
    if campaign.problem_type not in HULL_PROBLEMS:
        raise ViewNotApplicable("hull view applies to alloy campaigns only")

    from .problems.alloy import build_alloy_state

    state = await build_alloy_state(session, campaign)
    model = await latest_model(session, campaign.id)
    structures = (
        (
            await session.execute(
                select(Structure)
                .where(Structure.campaign_id == campaign.id)
                .order_by(Structure.label)
            )
        )
        .scalars()
        .all()
    )
    id_by_label = {s.label: s.id for s in structures}
    e_form_by_label = {m.label: m.e_form for m in state.measurements}
    stable = set(state.predicted_stable)

    points = [
        HullPoint(
            structure_id=id_by_label.get(p.label, ""),
            label=p.label,
            x=p.x,
            e_form=e_form_by_label.get(p.label) if p.measured else p.e_form_mean,
            e_form_std=0.0 if p.measured else p.e_form_std,
            measured=p.measured,
            predicted_stable=p.label in stable,
        )
        for p in state.pool_predictions
    ]
    return AlloyHullView(
        campaign_id=campaign.id,
        model_version=model.version if model else None,
        loocv_rmse=model.validation_metrics.get("loocv_rmse") if model else None,
        points=points,
        hull_x=model.artifact.get("hull_x", []) if model else [],
        hull_e=model.artifact.get("hull_e", []) if model else [],
        stable_labels=state.predicted_stable,
        endpoints_measured=state.endpoints_measured,
        energy_unit=energy_unit(campaign),
        engine=campaign.engine,
    )


async def candidates_view(session: AsyncSession, campaign: Campaign) -> CandidatesView:
    """Ranked candidates for property campaigns (plan section 14)."""
    if campaign.problem_type != "property_v3":
        raise ViewNotApplicable("candidates apply to property campaigns only")
    from .problems.property import build_property_state

    state = await build_property_state(session, campaign)
    return CandidatesView(
        campaign_id=campaign.id,
        temperature_threshold=state.temperature_threshold,
        model_version=state.latest_model.version if state.latest_model else None,
        top_candidate_label=state.top_candidate_label,
        candidates=[CandidateRead(**c.model_dump()) for c in state.candidates],
    )


async def phase_diagram_view(session: AsyncSession, campaign: Campaign) -> PhaseDiagramView:
    """T-x phase-diagram view: per-slice boundary estimates, curves, measurements."""
    if campaign.problem_type != "phase_v2":
        raise ViewNotApplicable("phase diagram applies to phase campaigns only")
    from .problems.phase import build_phase_state

    state = await build_phase_state(session, campaign)
    model = await latest_model(session, campaign.id)
    curves_by_x: dict = {}
    if model is not None:
        for entry in model.artifact.get("slices", []):
            curves_by_x[round(float(entry["x"]), 6)] = entry

    slices = []
    for s in state.slices:
        entry = curves_by_x.get(round(s.x, 6), {})
        slices.append(
            PhaseSliceView(
                x=s.x,
                tc_mean=s.tc_mean,
                tc_std=s.tc_std,
                tc_edge_pinned=s.tc_edge_pinned,
                curve_t=entry.get("curve_t", []),
                curve_mean=entry.get("curve_mean", []),
                curve_std=entry.get("curve_std", []),
                measured=[
                    PhaseMeasurementView(
                        calculation_id=m.calculation_id,
                        temperature=m.temperature,
                        heat_capacity=m.heat_capacity,
                        heat_capacity_err=m.heat_capacity_err,
                        sro=m.sro,
                    )
                    for m in s.measurements
                ],
            )
        )
    return PhaseDiagramView(
        campaign_id=campaign.id,
        model_version=model.version if model else None,
        temperature_min=campaign.temperature_min,
        temperature_max=campaign.temperature_max,
        slices=slices,
    )
