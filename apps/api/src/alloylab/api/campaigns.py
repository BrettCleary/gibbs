from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from ..agent.llm import LLMDecider
from ..agent.loop import runner_registry
from ..config import get_settings
from ..db.models import AgentEvent, Calculation, Campaign, SurrogateModel
from ..events import event_bus, sse_format
from .deps import get_session
from ..schemas import (
    AgentEventRead,
    CalculationRead,
    CampaignCreate,
    CampaignRead,
    CampaignSurrogateView,
    StartResponse,
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
    campaign = Campaign(
        name=body.name,
        objective=body.objective,
        problem_type="ising_v0",
        strategy=body.strategy.value,
        temperature_min=body.temperature_min,
        temperature_max=body.temperature_max,
        lattice_size=body.lattice_size,
        simulation_budget=body.simulation_budget,
        target_uncertainty=body.target_uncertainty,
        failure_rate=body.failure_rate,
        elements=["Ising spin"],
    )
    session.add(campaign)
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


@router.get("/{campaign_id}/events")
async def stream_events(campaign_id: str, request: Request):
    """Server-Sent Events: live agent actions, job lifecycle, model updates."""

    async def generator():
        async for event in event_bus.subscribe(campaign_id):
            if await request.is_disconnected():
                break
            yield sse_format(event)

    return EventSourceResponse(generator())
