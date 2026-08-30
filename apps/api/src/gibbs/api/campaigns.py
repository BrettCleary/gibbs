from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..agent.loop import runner_registry
from ..config import get_settings
from ..db.models import AgentEvent, Calculation, Campaign, Structure, SurrogateModel
from ..events import event_bus, sse_format
from .. import views
from .deps import get_session
from ..schemas import (
    AgentEventRead,
    AlloyHullView,
    CalculationRead,
    CampaignCreate,
    DEFAULT_ELEMENTS,
    ElementRead,
    FCC_PROBLEMS,
    CandidatesView,
    CampaignReport,
    CampaignRead,
    CampaignSurrogateView,
    PhaseDiagramView,
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


async def _view(builder, session: AsyncSession, campaign_id: str):
    campaign = await _get_campaign(session, campaign_id)
    try:
        return await builder(session, campaign)
    except views.ViewNotApplicable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("", response_model=CampaignRead, status_code=201)
async def create_campaign(body: CampaignCreate, session: AsyncSession = Depends(get_session)):
    is_alloy = body.problem_type.value in ("alloy_v1", "fcc_v2", "dft_v3", "property_v3")
    is_phase = body.problem_type.value == "phase_v2"
    # Element pair for the FCC problems (default Ni-Al): parent lattice = element A.
    elements = list(body.elements or DEFAULT_ELEMENTS)
    lattice: dict = {}
    if body.problem_type in FCC_PROBLEMS:
        from alloyscience.calculators import fcc_lattice_constant

        try:
            a_by_element = {el: fcc_lattice_constant(el) for el in elements}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        lattice = {"elements": elements, "a_parent": a_by_element[elements[0]], "a_by_element": a_by_element}
        engine = body.property_engine.value if body.problem_type.value == "property_v3" else (
            body.dft_engine.value if body.problem_type.value == "dft_v3" else None)
        if engine == "emt":
            from alloyscience.calculators import EMT_ELEMENTS

            bad = [e for e in elements if e not in EMT_ELEMENTS]
            if bad:
                raise HTTPException(status_code=400, detail=f"EMT has no parameters for {bad}; supported: {sorted(EMT_ELEMENTS)}")
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
        # Testing seam, not a user input: 0.0 unless a local/CI operator sets it.
        failure_rate=get_settings().injected_failure_rate,
        elements=(
            ["A", "B"] if body.problem_type.value == "alloy_v1"
            else elements if body.problem_type in FCC_PROBLEMS
            else ["Ising spin"]
        ),
    )
    session.add(campaign)
    await session.flush()
    if is_phase:
        from alloyscience.fcc import HiddenFccCE
        from alloyscience.phase import phase_system

        from ..agent.strategies import stable_seed

        seed = stable_seed(campaign.id)
        system = await run_in_threadpool(phase_system, lattice["a_parent"], tuple(elements))
        campaign.problem_config = {
            **lattice,
            "kind": "fcc_phase",
            "hamiltonian": HiddenFccCE.random(
                system.n_parameters, seed=seed, noise_sigma=0.0
            ).to_dict(),
            "slices": body.composition_slices or [0.25, 0.5, 0.75],
            "oracle_seed": seed % 1_000_000,
        }
    elif body.problem_type.value == "property_v3":
        from alloyscience.fcc import HiddenFccCE
        from alloyscience.property import HiddenBulkModulusModel
        from alloyscience.property.benchmark import property_pool

        from ..agent.strategies import stable_seed

        seed = stable_seed(campaign.id)
        system, pool = await run_in_threadpool(property_pool, 5, lattice["a_parent"], tuple(elements))
        hidden = HiddenFccCE.random(system.n_parameters, seed=seed)
        pure_a = next(s for s in pool if s.x == 0.0)
        pure_b = next(s for s in pool if s.x == 1.0)
        config = {
            **lattice,
            "kind": "property",
            "engine": body.property_engine.value,
            "t_threshold": body.temperature_threshold,
            "max_size": 3 if body.property_engine.value == "espresso" else 5,
            "hamiltonian": hidden.to_dict(),
            "b_model": HiddenBulkModulusModel.random(seed).to_dict(),
            "e_pure_a": hidden.energy_per_site(pure_a),
            "e_pure_b": hidden.energy_per_site(pure_b),
            "oracle_seed": seed % 1_000_000,
        }
        if body.property_engine.value == "espresso":
            from alloyscience.calculators import EspressoConfig, espresso_available

            espresso_config = _espresso_config_for(elements, lattice["a_parent"], kspacing=0.35, n_volumes=5)
            config["espresso"] = espresso_config.to_dict()
        campaign.problem_config = config
    elif body.problem_type.value == "dft_v3":
        # No hidden physics here — a real energy engine answers the queries.
        engine = body.dft_engine.value
        config: dict = {**lattice, "kind": "ase_calculator", "engine": engine}
        if engine == "espresso":
            # Demo-grade k-mesh: qualitatively correct formation energies at minutes/structure.
            config["espresso"] = _espresso_config_for(elements, lattice["a_parent"], kspacing=0.35).to_dict()
            config["max_size"] = 4  # real DFT: keep enumerated cells small
        else:
            config["max_size"] = 5
        campaign.problem_config = config
    elif is_alloy:
        # The secret physics: generated per campaign, visible only to the executor.
        from ..agent.strategies import stable_seed

        seed = stable_seed(campaign.id)
        if body.problem_type.value == "fcc_v2":
            from alloyscience.fcc import HiddenFccCE
            from alloyscience.fcc.system import cached_system_and_pool

            from alloyscience.fcc.system import cutoffs_for

            system, _ = await run_in_threadpool(
                cached_system_and_pool, lattice["a_parent"], cutoffs_for(lattice["a_parent"]), tuple(elements)
            )
            campaign.problem_config = {
                **lattice,
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


def _espresso_config_for(elements: list[str], a_parent: float, **overrides):
    """EspressoConfig for an element pair, resolving pseudopotentials from the
    configured pseudo_dir; 400 with a fetch hint when any are missing."""
    from alloyscience.calculators import EspressoConfig, espresso_available, resolve_pseudopotentials

    settings = get_settings()
    found, missing = resolve_pseudopotentials(settings.pseudo_dir, elements)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"no pseudopotential for {missing} in {settings.pseudo_dir}; run "
            f"`uv run --package gibbs python -m gibbs.pseudos {' '.join(elements)}` to fetch PSlibrary PAW sets",
        )
    config = EspressoConfig(
        pw_command=settings.pw_command, pseudo_dir=settings.pseudo_dir,
        pseudopotentials=found, a_parent=a_parent, **overrides,
    )
    # Under Temporal, pw.x runs on the worker fleet, not here: the API may be a
    # web container with no QE installed (and no way to install one). The
    # pseudopotentials are already resolved above, so only the binary check is
    # host-specific — skip it and let the worker report an ENGINE_UNAVAILABLE
    # failure if it is the one that is misconfigured.
    if settings.executor == "temporal":
        return config
    ok, reason = espresso_available(config)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"Quantum ESPRESSO engine unavailable: {reason}. Set ALLOYLAB_PW_COMMAND or use the emt engine.",
        )
    return config


@router.get("/elements", response_model=list[ElementRead])
async def list_elements():
    """The element catalog for the campaign form, with per-engine support.

    Espresso support means a pseudopotential is present in the configured
    pseudo_dir (fetch with `python -m gibbs.pseudos <El>`)."""
    from alloyscience.calculators import element_catalog, resolve_pseudopotentials

    settings = get_settings()
    catalog = element_catalog()
    found, _ = resolve_pseudopotentials(settings.pseudo_dir, [e.symbol for e in catalog])
    out = []
    for e in catalog:
        note = None
        if not e.fcc_native:
            note = (
                f"{e.symbol} is {e.structure.upper()} at ambient conditions; campaigns model a "
                f"hypothetical FCC lattice (a = {e.a_fcc:.2f} Å, equal atomic volume)."
            )
        out.append(
            ElementRead(
                symbol=e.symbol, name=e.name, atomic_number=e.atomic_number,
                structure=e.structure, fcc_native=e.fcc_native, a_fcc=round(e.a_fcc, 3),
                engines={"hidden": True, "emt": e.emt, "espresso": e.symbol in found},
                note=note,
            )
        )
    return out


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
    if campaign.strategy == "agent":
        from ..agent.llm import model_available

        ok, reason = model_available(get_settings().agent_model)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail=f"strategy 'agent' unavailable: {reason}; set the key, change "
                "ALLOYLAB_AGENT_MODEL, or use a heuristic strategy (random/grid/uncertainty)",
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
    return await _view(views.hull_view, session, campaign_id)


@router.get("/{campaign_id}/report", response_model=CampaignReport)
async def get_report(campaign_id: str, session: AsyncSession = Depends(get_session)):
    """Final scientific report (plan section 16). Persisted at completion;
    generated on the fly for campaigns still in progress."""
    campaign = await _get_campaign(session, campaign_id)
    if campaign.report:
        return CampaignReport(**campaign.report)
    from ..report import build_report

    return CampaignReport(**(await build_report(session, campaign)))


@router.get("/{campaign_id}/candidates", response_model=CandidatesView)
async def get_candidates(campaign_id: str, session: AsyncSession = Depends(get_session)):
    """Ranked candidates for property campaigns (plan section 14)."""
    return await _view(views.candidates_view, session, campaign_id)


@router.get("/{campaign_id}/phase-diagram", response_model=PhaseDiagramView)
async def get_phase_diagram(campaign_id: str, session: AsyncSession = Depends(get_session)):
    """T-x phase-diagram view: per-slice boundary estimates, curves, measurements."""
    return await _view(views.phase_diagram_view, session, campaign_id)


@router.get("/{campaign_id}/events")
async def stream_events(campaign_id: str, request: Request):
    """Server-Sent Events: live agent actions, job lifecycle, model updates."""

    async def generator():
        async for event in event_bus.subscribe(campaign_id):
            if await request.is_disconnected():
                break
            yield sse_format(event)

    return EventSourceResponse(generator())
