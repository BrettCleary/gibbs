from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..agent.llm import LLMDecider
from ..agent.loop import runner_registry
from ..config import get_settings
from ..db.models import AgentEvent, Calculation, Campaign, Structure, SurrogateModel
from ..events import event_bus, sse_format
from .deps import get_session
from ..schemas import (
    AgentEventRead,
    AlloyHullView,
    CalculationRead,
    CampaignCreate,
    CampaignRead,
    CampaignSurrogateView,
    HullPoint,
    PhaseDiagramView,
    PhaseMeasurementView,
    PhaseSliceView,
    StartResponse,
    StructureRead,
    SurrogateModelRead,
)

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


async def _get_campaign(session: AsyncSession, campaign_id: str) -> Campaign:
    campaign = await session.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    return campaign


@router.post("", response_model=CampaignRead, status_code=201)
async def create_campaign(body: CampaignCreate, session: AsyncSession = Depends(get_session)):
    is_alloy = body.problem_type.value in ("alloy_v1", "fcc_v2")
    is_phase = body.problem_type.value == "phase_v2"
    t_min, t_max = body.temperature_min, body.temperature_max
    if is_phase and t_max <= 10.0:
        # Phase campaigns run in Kelvin; replace untouched Ising-unit defaults.
        # The window brackets the Tc range of the hidden-ECI distribution.
        t_min, t_max = 100.0, 1200.0
    campaign = Campaign(
        name=body.name,
        objective=body.objective,
        problem_type=body.problem_type.value,
        strategy=body.strategy.value,
        temperature_min=t_min,
        temperature_max=t_max,
        composition_min=(body.composition_min if body.composition_min is not None else 0.0)
        if is_alloy
        else None,
        composition_max=(body.composition_max if body.composition_max is not None else 1.0)
        if is_alloy
        else None,
        lattice_size=body.lattice_size,
        simulation_budget=body.simulation_budget,
        target_uncertainty=body.target_uncertainty,
        failure_rate=body.failure_rate,
        elements={
            "alloy_v1": ["A", "B"],
            "fcc_v2": ["Ni", "Al"],
            "phase_v2": ["Ni", "Al"],
        }.get(body.problem_type.value, ["Ising spin"]),
    )
    session.add(campaign)
    await session.flush()
    if is_phase:
        from alloyscience.fcc import HiddenFccCE
        from alloyscience.phase import phase_system

        from ..agent.strategies import stable_seed

        seed = stable_seed(campaign.id)
        system = await run_in_threadpool(phase_system)
        campaign.problem_config = {
            "kind": "fcc_phase",
            "hamiltonian": HiddenFccCE.random(
                system.n_parameters, seed=seed, noise_sigma=0.0
            ).to_dict(),
            "slices": body.composition_slices or [0.25, 0.5, 0.75],
            "oracle_seed": seed % 1_000_000,
        }
    elif is_alloy:
        # The secret physics: generated per campaign, visible only to the executor.
        from ..agent.strategies import stable_seed

        seed = stable_seed(campaign.id)
        if body.problem_type.value == "fcc_v2":
            from alloyscience.fcc import HiddenFccCE
            from alloyscience.fcc.system import cached_system_and_pool

            system, _ = await run_in_threadpool(cached_system_and_pool)
            campaign.problem_config = {
                "kind": "fcc_ce",
                "hamiltonian": HiddenFccCE.random(system.n_parameters, seed=seed).to_dict(),
                "oracle_seed": seed % 1_000_000,
            }
        else:
            from alloyscience.alloy import HiddenPairHamiltonian

            campaign.problem_config = {
                "kind": "pair_hamiltonian",
                "hamiltonian": HiddenPairHamiltonian.random(seed=seed).to_dict(),
                "oracle_seed": seed % 1_000_000,
            }
    await session.commit()
    return campaign


@router.get("", response_model=list[CampaignRead])
async def list_campaigns(session: AsyncSession = Depends(get_session)):
    rows = await session.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    return rows.scalars().all()


@router.get("/{campaign_id}", response_model=CampaignRead)
async def get_campaign(campaign_id: str, session: AsyncSession = Depends(get_session)):
    return await _get_campaign(session, campaign_id)


@router.post("/{campaign_id}/start", response_model=StartResponse)
async def start_campaign(campaign_id: str, session: AsyncSession = Depends(get_session)):
    campaign = await _get_campaign(session, campaign_id)
    if campaign.status in ("COMPLETED", "FAILED"):
        raise HTTPException(status_code=409, detail=f"campaign is {campaign.status}")
    if runner_registry.is_running(campaign_id):
        raise HTTPException(status_code=409, detail="campaign is already running")
    if campaign.strategy == "agent" and not LLMDecider.available():
        raise HTTPException(
            status_code=400,
            detail="strategy 'agent' requires OPENAI_API_KEY in the API environment; "
            "set it or use a heuristic strategy (random/grid/uncertainty)",
        )
    campaign.status = "RUNNING"
    await session.commit()
    model = get_settings().agent_model if campaign.strategy == "agent" else "heuristic"
    agent_run_id = await runner_registry.start(campaign_id, model=model)
    return StartResponse(campaign_id=campaign_id, status="RUNNING", agent_run_id=agent_run_id)


@router.post("/{campaign_id}/pause", response_model=CampaignRead)
async def pause_campaign(campaign_id: str, session: AsyncSession = Depends(get_session)):
    campaign = await _get_campaign(session, campaign_id)
    if campaign.status != "RUNNING":
        raise HTTPException(status_code=409, detail="campaign is not running")
    campaign.status = "PAUSED"
    await session.commit()
    return campaign


@router.get("/{campaign_id}/calculations", response_model=list[CalculationRead])
async def list_calculations(campaign_id: str, session: AsyncSession = Depends(get_session)):
    await _get_campaign(session, campaign_id)
    rows = await session.execute(
        select(Calculation)
        .where(Calculation.campaign_id == campaign_id)
        .order_by(Calculation.created_at)
    )
    return rows.scalars().all()


@router.get("/{campaign_id}/models", response_model=list[SurrogateModelRead])
async def list_models(campaign_id: str, session: AsyncSession = Depends(get_session)):
    await _get_campaign(session, campaign_id)
    rows = await session.execute(
        select(SurrogateModel)
        .where(SurrogateModel.campaign_id == campaign_id)
        .order_by(SurrogateModel.version)
    )
    return rows.scalars().all()


@router.get("/{campaign_id}/agent-events", response_model=list[AgentEventRead])
async def list_agent_events(
    campaign_id: str, limit: int = 200, session: AsyncSession = Depends(get_session)
):
    await _get_campaign(session, campaign_id)
    rows = await session.execute(
        select(AgentEvent)
        .where(AgentEvent.campaign_id == campaign_id)
        .order_by(AgentEvent.created_at.desc())
        .limit(limit)
    )
    return list(reversed(rows.scalars().all()))


@router.get("/{campaign_id}/surrogate", response_model=CampaignSurrogateView)
async def get_surrogate_view(campaign_id: str, session: AsyncSession = Depends(get_session)):
    """Latest surrogate curve plus the measured points it was trained on."""
    await _get_campaign(session, campaign_id)
    model = (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign_id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    calcs = (
        (
            await session.execute(
                select(Calculation)
                .where(
                    Calculation.campaign_id == campaign_id,
                    Calculation.status == "SUCCEEDED",
                )
                .order_by(Calculation.created_at)
            )
        )
        .scalars()
        .all()
    )
    return CampaignSurrogateView(
        campaign_id=campaign_id,
        model_version=model.version if model else None,
        temperatures=model.artifact.get("temperatures", []) if model else [],
        mean=model.artifact.get("mean", []) if model else [],
        std=model.artifact.get("std", []) if model else [],
        measured_temperatures=[float(c.input_parameters["temperature"]) for c in calcs],
        measured_values=[float(c.output["susceptibility"]) for c in calcs],
        measured_errors=[float(c.output["susceptibility_err"]) for c in calcs],
        measured_calculation_ids=[c.id for c in calcs],
        tc_mean=model.validation_metrics.get("tc_mean") if model else None,
        tc_std=model.validation_metrics.get("tc_std") if model else None,
    )


@router.get("/{campaign_id}/structures", response_model=list[StructureRead])
async def list_structures(campaign_id: str, session: AsyncSession = Depends(get_session)):
    await _get_campaign(session, campaign_id)
    rows = await session.execute(
        select(Structure).where(Structure.campaign_id == campaign_id).order_by(Structure.label)
    )
    return rows.scalars().all()


@router.get("/{campaign_id}/hull", response_model=AlloyHullView)
async def get_hull_view(campaign_id: str, session: AsyncSession = Depends(get_session)):
    """Formation-energy hull view for alloy campaigns: measurements, predictions, hull."""
    campaign = await _get_campaign(session, campaign_id)
    if campaign.problem_type not in ("alloy_v1", "fcc_v2"):
        raise HTTPException(status_code=400, detail="hull view applies to alloy campaigns only")

    from ..problems.alloy import build_alloy_state

    state = await build_alloy_state(session, campaign)
    model = (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign_id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    structures = (
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
    id_by_label = {s.label: s.id for s in structures}
    e_form_by_label = {m.label: m.e_form for m in state.measurements}

    points = []
    for p in state.pool_predictions:
        measured_e_form = e_form_by_label.get(p.label)
        points.append(
            HullPoint(
                structure_id=id_by_label.get(p.label, ""),
                label=p.label,
                x=p.x,
                e_form=measured_e_form if p.measured else p.e_form_mean,
                e_form_std=0.0 if p.measured else p.e_form_std,
                measured=p.measured,
                predicted_stable=p.label in set(state.predicted_stable),
            )
        )

    hull_x: list[float] = []
    hull_e: list[float] = []
    loocv = None
    if model is not None:
        hull_x = model.artifact.get("hull_x", [])
        hull_e = model.artifact.get("hull_e", [])
        loocv = model.validation_metrics.get("loocv_rmse")

    return AlloyHullView(
        campaign_id=campaign_id,
        model_version=model.version if model else None,
        loocv_rmse=loocv,
        points=points,
        hull_x=hull_x,
        hull_e=hull_e,
        stable_labels=state.predicted_stable,
        endpoints_measured=state.endpoints_measured,
    )


@router.get("/{campaign_id}/phase-diagram", response_model=PhaseDiagramView)
async def get_phase_diagram(campaign_id: str, session: AsyncSession = Depends(get_session)):
    """T-x phase-diagram view: per-slice boundary estimates, curves, measurements."""
    campaign = await _get_campaign(session, campaign_id)
    if campaign.problem_type != "phase_v2":
        raise HTTPException(
            status_code=400, detail="phase diagram applies to phase campaigns only"
        )
    from ..problems.phase import build_phase_state

    state = await build_phase_state(session, campaign)
    model = (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign_id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
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
        campaign_id=campaign_id,
        model_version=model.version if model else None,
        temperature_min=campaign.temperature_min,
        temperature_max=campaign.temperature_max,
        slices=slices,
    )


@router.get("/{campaign_id}/events")
async def stream_events(campaign_id: str, request: Request):
    """Server-Sent Events: live agent actions, job lifecycle, model updates."""

    async def generator():
        async for event in event_bus.subscribe(campaign_id):
            if await request.is_disconnected():
                break
            yield sse_format(event)

    return EventSourceResponse(generator())
