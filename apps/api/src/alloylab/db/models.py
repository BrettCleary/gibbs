from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Campaign(Base):
    """A discovery campaign. V0: locate the Ising critical region."""

    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    objective: Mapped[str] = mapped_column(Text)
    problem_type: Mapped[str] = mapped_column(String(50), default="ising_v0")
    strategy: Mapped[str] = mapped_column(String(50), default="agent")

    # Search space (V0: temperature only; composition reserved for V1+).
    temperature_min: Mapped[float] = mapped_column(Float, default=1.5)
    temperature_max: Mapped[float] = mapped_column(Float, default=3.5)
    composition_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    composition_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    elements: Mapped[list] = mapped_column(JSON, default=list)

    lattice_size: Mapped[int] = mapped_column(Integer, default=24)
    simulation_budget: Mapped[int] = mapped_column(Integer, default=20)
    simulations_used: Mapped[int] = mapped_column(Integer, default=0)
    target_uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_rate: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(String(30), default="CREATED")
    stopping_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Calculation(Base):
    """One simulation job (V0: a Monte Carlo run at one temperature)."""

    __tablename__ = "calculations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    calculation_type: Mapped[str] = mapped_column(String(40), default="MONTE_CARLO")
    engine: Mapped[str] = mapped_column(String(100), default="alloyscience.ising.IsingSimulator")
    status: Mapped[str] = mapped_column(String(20), default="QUEUED", index=True)

    input_parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provenance: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    failure_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    failure_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_of: Mapped[str | None] = mapped_column(ForeignKey("calculations.id"), nullable=True)
    changed_parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason_for_change: Mapped[str | None] = mapped_column(Text, nullable=True)
    # null | "retried" | "abandoned" — how a FAILED calculation was dealt with.
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SurrogateModel(Base):
    """A fitted surrogate (V0: bootstrap response surrogate for chi(T))."""

    __tablename__ = "surrogate_models"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    type: Mapped[str] = mapped_column(String(50), default="response_surrogate")
    version: Mapped[int] = mapped_column(Integer, default=1)
    training_calculation_ids: Mapped[list] = mapped_column(JSON, default=list)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    artifact: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgentRun(Base):
    """One autonomous run of the scientist loop over a campaign."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    model: Mapped[str] = mapped_column(String(100), default="heuristic")
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AgentEvent(Base):
    """Auditable record of every agent decision/action and job lifecycle event."""

    __tablename__ = "agent_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    agent_run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    hypothesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_output_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BenchmarkRun(Base):
    """A stored benchmark comparison of experiment-selection strategies."""

    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
