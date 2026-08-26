"""Structured agent decisions (plan section 29).

Every important choice the scientist makes — heuristic or LLM — is forced into
this schema, persisted as an AgentEvent, and displayed by the frontend. Raw
model reasoning is never stored; only this explicit scientific rationale.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    RUN_MONTE_CARLO = "RUN_MONTE_CARLO"
    RETRY_CALCULATION = "RETRY_CALCULATION"
    ABANDON_CALCULATION = "ABANDON_CALCULATION"
    FINISH_CAMPAIGN = "FINISH_CAMPAIGN"


class ScientificDecision(BaseModel):
    hypothesis: str
    evidence: list[str] = Field(default_factory=list)
    uncertainty: str = ""
    action_type: ActionType
    temperatures: list[float] = Field(
        default_factory=list,
        description="Temperatures for RUN_MONTE_CARLO (at most 3 per decision).",
    )
    retry_calculation_id: str | None = Field(
        default=None, description="Failed calculation id for RETRY/ABANDON actions."
    )
    adjusted_parameters: dict[str, float] | None = Field(
        default=None, description="Parameter overrides for a retry."
    )
    reason_for_change: str | None = None
    expected_information_gain: str = ""
    stopping_rationale: str | None = None
