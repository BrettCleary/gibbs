"""Summarised scientific state handed to the deciding agent (plan section 28).

`BaseScientificState` carries what every problem shares (budget, failures,
latest surrogate); each problem adapter extends it with its own summary
(Ising: chi(T) measurements; alloy: structure pool + hull predictions).
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from alloyscience.benchmark import AcquisitionState
from alloyscience.surrogate import ResponseSurrogate

from ..db.models import Calculation, Campaign, SurrogateModel


class FailureRecord(BaseModel):
    calculation_id: str
    description: str  # human-readable target, e.g. "T=2.300" or "structure s034-2x3"
    category: str
    metadata: dict
    is_retry: bool


class ModelSummary(BaseModel):
    version: int
    n_training_points: int
    uncertainty_metric: float | None = None  # compared against campaign.target_uncertainty
    summary_text: str = ""


class BaseScientificState(BaseModel):
    campaign_id: str
    objective: str
    strategy: str
    budget_total: int
    budget_used: int
    budget_remaining: int
    target_uncertainty: float | None
    unresolved_failures: list[FailureRecord] = Field(default_factory=list)
    latest_model: ModelSummary | None = None


class Measurement(BaseModel):
    calculation_id: str
    temperature: float
    susceptibility: float
    susceptibility_err: float


class ScientificState(BaseScientificState):
    """Ising V0 state: chi(T) measurements over a temperature range."""

    temperature_min: float
    temperature_max: float
    lattice_size: int
    measurements: list[Measurement] = Field(default_factory=list)
    suggested_uncertainty_temperature: float | None = None

    def acquisition_state(self) -> AcquisitionState:
        return AcquisitionState(
            t_min=self.temperature_min,
            t_max=self.temperature_max,
            measured_temperatures=[m.temperature for m in self.measurements],
            measured_values=[m.susceptibility for m in self.measurements],
            measured_errors=[m.susceptibility_err for m in self.measurements],
            remaining_budget=self.budget_remaining,
        )


async def load_campaign_calculations(
    session: AsyncSession, campaign_id: str
) -> list[Calculation]:
    return (
        (
            await session.execute(
                select(Calculation)
                .where(Calculation.campaign_id == campaign_id)
                .order_by(Calculation.created_at)
            )
        )
        .scalars()
        .all()
    )


def budget_used(calcs: list[Calculation]) -> int:
    return sum(1 for c in calcs if c.status in ("SUCCEEDED", "FAILED", "RUNNING"))


def unresolved_failures(
    calcs: list[Calculation], describe
) -> list[FailureRecord]:
    return [
        FailureRecord(
            calculation_id=c.id,
            description=describe(c),
            category=c.failure_category or "UNKNOWN",
            metadata=c.failure_metadata or {},
            is_retry=c.retry_of is not None,
        )
        for c in calcs
        if c.status == "FAILED" and c.resolution is None
    ]


async def latest_surrogate_model(
    session: AsyncSession, campaign_id: str
) -> SurrogateModel | None:
    return (
        await session.execute(
            select(SurrogateModel)
            .where(SurrogateModel.campaign_id == campaign_id)
            .order_by(SurrogateModel.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def build_scientific_state(session: AsyncSession, campaign: Campaign) -> ScientificState:
    """State builder for the Ising V0 problem."""
    calcs = await load_campaign_calculations(session, campaign.id)

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

    latest = await latest_surrogate_model(session, campaign.id)
    latest_model = None
    if latest is not None:
        tc_mean = latest.validation_metrics.get("tc_mean")
        tc_std = latest.validation_metrics.get("tc_std")
        latest_model = ModelSummary(
            version=latest.version,
            n_training_points=len(latest.training_calculation_ids),
            uncertainty_metric=tc_std,
            summary_text=(
                f"Tc = {tc_mean:.4f} ± {tc_std:.4f} (surrogate v{latest.version})"
                if tc_mean is not None
                else f"surrogate v{latest.version}"
            ),
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

    used = budget_used(calcs)
    return ScientificState(
        campaign_id=campaign.id,
        objective=campaign.objective,
        strategy=campaign.strategy,
        temperature_min=campaign.temperature_min,
        temperature_max=campaign.temperature_max,
        lattice_size=campaign.lattice_size,
        budget_total=campaign.simulation_budget,
        budget_used=used,
        budget_remaining=max(campaign.simulation_budget - used, 0),
        target_uncertainty=campaign.target_uncertainty,
        measurements=measurements,
        unresolved_failures=unresolved_failures(
            calcs,
            lambda c: f"T={float(c.input_parameters.get('temperature', 0.0)):.3f}",
        ),
        latest_model=latest_model,
        suggested_uncertainty_temperature=suggestion,
    )
