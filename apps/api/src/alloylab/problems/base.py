"""Problem adapters: everything problem-specific behind one interface.

The campaign loop, executor plumbing, failure policy, budget accounting, and
event stream are shared; a Problem supplies the science — state building,
decision validation, calculation creation, and model updates. Adding V2+
(icet, real DFT) means adding an adapter, not touching the loop.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from ..agent.decisions import ScientificDecision
from ..agent.state import BaseScientificState
from ..agent.strategies import Decider
from ..db.models import Campaign

MAX_TARGETS_PER_DECISION = 3


class Problem(Protocol):
    problem_type: str

    async def initialize(self, session: AsyncSession, campaign: Campaign) -> None:
        """Idempotent setup on campaign start (e.g. enumerate the structure pool)."""
        ...

    async def build_state(
        self, session: AsyncSession, campaign: Campaign
    ) -> BaseScientificState: ...

    def decider(self, campaign: Campaign) -> Decider: ...

    def validate(
        self, state: BaseScientificState, decision: ScientificDecision
    ) -> ScientificDecision: ...

    async def create_calculations(
        self, session: AsyncSession, campaign: Campaign, decision: ScientificDecision
    ) -> list[str]:
        """Create QUEUED calculation rows for a RUN_* decision; return their ids."""
        ...

    async def update_models(
        self, session: AsyncSession, campaign: Campaign, agent_run_id: str | None
    ) -> None: ...

    def describe_action(self, decision: ScientificDecision) -> str: ...


def get_problem(campaign: Campaign) -> Problem:
    from .alloy import AlloyProblem
    from .fcc import FccProblem
    from .ising import IsingProblem

    problems = {"ising_v0": IsingProblem, "alloy_v1": AlloyProblem, "fcc_v2": FccProblem}
    if campaign.problem_type not in problems:
        raise ValueError(f"unknown problem type {campaign.problem_type!r}")
    return problems[campaign.problem_type]()
