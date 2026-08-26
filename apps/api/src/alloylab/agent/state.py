"""Build the summarised scientific state handed to the deciding agent.

Summaries, not raw arrays (plan section 28): measurements, surrogate metrics,
uncertainty suggestions, unresolved failures, and budget.
"""

from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.benchmark import AcquisitionState
from alloyscience.surrogate import ResponseSurrogate

from ..db.models import Calculation, Campaign, SurrogateModel


class Measurement(BaseModel):
    calculation_id: str
    temperature: float
    susceptibility: float
    susceptibility_err: float


class FailureRecord(BaseModel):
    calculation_id: str
    temperature: float
    category: str
    metadata: dict
    is_retry: bool


class ModelSummary(BaseModel):
    version: int
    tc_mean: float | None
    tc_std: float | None
    n_training_points: int


class ScientificState(BaseModel):
    campaign_id: str
    objective: str
    strategy: str
    temperature_min: float
    temperature_max: float
    lattice_size: int
    budget_total: int
    budget_used: int
    budget_remaining: int
    target_uncertainty: float | None
    measurements: list[Measurement]
    unresolved_failures: list[FailureRecord]
    latest_model: ModelSummary | None
    suggested_uncertainty_temperature: float | None

    def acquisition_state(self) -> AcquisitionState:
        return AcquisitionState(
            t_min=self.temperature_min,
            t_max=self.temperature_max,
            measured_temperatures=[m.temperature for m in self.measurements],
            measured_values=[m.susceptibility for m in self.measurements],
            measured_errors=[m.susceptibility_err for m in self.measurements],
            remaining_budget=self.budget_remaining,
        )


async def build_scientific_state(session: AsyncSession, campaign: Campaign) -> ScientificState:
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

    measurements = [
        Measurement(
            calculation_id=c.id,
            temperature=float(c.input_parameters["temperature"]),
            susceptibility=float(c.output["susceptibility"]),
            susceptibility_err=float(c.output["susceptibility_err"]),
        )
        for c in calcs
        if c.status == "SUCCEEDED" and c.output
    ]

    unresolved = [
        FailureRecord(
            calculation_id=c.id,
            temperature=float(c.input_parameters.get("temperature", 0.0)),
            category=c.failure_category or "UNKNOWN",
            metadata=c.failure_metadata or {},
            is_retry=c.retry_of is not None,
        )
        for c in calcs
        if c.status == "FAILED" and c.resolution is None
    ]

    latest = (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign.id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    latest_model = (
        ModelSummary(
            version=latest.version,
            tc_mean=latest.validation_metrics.get("tc_mean"),
            tc_std=latest.validation_metrics.get("tc_std"),
            n_training_points=len(latest.training_calculation_ids),
        )
        if latest
        else None
    )

    suggestion = None
    if len(measurements) >= ResponseSurrogate.MIN_POINTS:
        surrogate = ResponseSurrogate(
            [m.temperature for m in measurements],
            [m.susceptibility for m in measurements],
            [m.susceptibility_err for m in measurements],
            seed=0,
        )
        suggestion = surrogate.suggest_highest_uncertainty(
            campaign.temperature_min,
            campaign.temperature_max,
            exclude=[m.temperature for m in measurements],
        )

    budget_used = sum(1 for c in calcs if c.status in ("SUCCEEDED", "FAILED", "RUNNING"))
    return ScientificState(
        campaign_id=campaign.id,
        objective=campaign.objective,
        strategy=campaign.strategy,
        temperature_min=campaign.temperature_min,
        temperature_max=campaign.temperature_max,
        lattice_size=campaign.lattice_size,
        budget_total=campaign.simulation_budget,
        budget_used=budget_used,
        budget_remaining=max(campaign.simulation_budget - budget_used, 0),
        target_uncertainty=campaign.target_uncertainty,
        measurements=measurements,
        unresolved_failures=unresolved,
        latest_model=latest_model,
        suggested_uncertainty_temperature=suggestion,
    )
