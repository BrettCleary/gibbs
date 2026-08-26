"""Deciders: map a scientific state to a structured ScientificDecision.

Generic policies (failure recovery, stopping) are shared by every problem so
benchmarks compare acquisition quality, not bookkeeping. The Ising heuristic
decider lives here; the alloy one lives in `problems/alloy.py`; the LLM
decider in `llm.py` satisfies the same protocol.
"""

from __future__ import annotations

import zlib
from typing import Protocol

from alloyscience.benchmark import make_strategy

from .decisions import ActionType, ScientificDecision
from .state import BaseScientificState, ScientificState


class Decider(Protocol):
    name: str

    async def decide(self, state: BaseScientificState) -> ScientificDecision: ...


def stable_seed(campaign_id: str) -> int:
    return zlib.crc32(campaign_id.encode())


def handle_failures(
    state: BaseScientificState,
    retry_adjustment: dict[str, float],
    retry_reason: str,
) -> ScientificDecision | None:
    """Shared failure-recovery policy: retry once with adjusted settings, then abandon."""
    if not state.unresolved_failures:
        return None
    failure = state.unresolved_failures[0]
    if failure.is_retry:
        return ScientificDecision(
            hypothesis=f"Calculation {failure.calculation_id} ({failure.description}) "
            "failed again after a retry with adjusted settings.",
            evidence=[f"failure category: {failure.category}", "retry also failed"],
            uncertainty="This target remains unmeasured; nearby measurements must compensate.",
            action_type=ActionType.ABANDON_CALCULATION,
            retry_calculation_id=failure.calculation_id,
            expected_information_gain="Avoid spending further budget on a pathological run.",
        )
    return ScientificDecision(
        hypothesis=f"Run for {failure.description} failed with {failure.category}; "
        "adjusted settings should converge.",
        evidence=[f"failure category: {failure.category}", str(failure.metadata)],
        uncertainty="The failed target carries no information until re-run.",
        action_type=ActionType.RETRY_CALCULATION,
        retry_calculation_id=failure.calculation_id,
        adjusted_parameters=retry_adjustment,
        reason_for_change=retry_reason,
        expected_information_gain="Recovers the planned measurement at the failed target.",
    )


def check_stopping(state: BaseScientificState) -> ScientificDecision | None:
    if state.budget_remaining <= 0:
        return ScientificDecision(
            hypothesis="The simulation budget is exhausted.",
            evidence=[f"{state.budget_used}/{state.budget_total} simulations consumed"],
            uncertainty=model_summary_text(state),
            action_type=ActionType.FINISH_CAMPAIGN,
            stopping_rationale="Simulation budget exhausted; reporting best current estimate.",
        )
    if (
        state.target_uncertainty is not None
        and state.latest_model is not None
        and state.latest_model.uncertainty_metric is not None
        and state.latest_model.uncertainty_metric < state.target_uncertainty
    ):
        return ScientificDecision(
            hypothesis="The model has reached the requested precision.",
            evidence=[
                model_summary_text(state),
                f"target uncertainty: {state.target_uncertainty}",
            ],
            uncertainty=model_summary_text(state),
            action_type=ActionType.FINISH_CAMPAIGN,
            stopping_rationale=(
                f"Model uncertainty {state.latest_model.uncertainty_metric:.4f} is below "
                f"the target {state.target_uncertainty}; further runs have low expected value."
            ),
        )
    return None


def model_summary_text(state: BaseScientificState) -> str:
    if state.latest_model:
        return state.latest_model.summary_text or f"surrogate v{state.latest_model.version}"
    return "No surrogate model fitted yet."


ISING_RETRY_ADJUSTMENT = {"n_equilibration_sweeps_factor": 3.0}
ISING_RETRY_REASON = "Tripled equilibration sweeps to address non-equilibrated chain."


class HeuristicDecider:
    """Ising V0: wraps a baseline acquisition strategy in the decision schema."""

    def __init__(self, strategy_name: str, seed: int = 0):
        self.name = strategy_name
        self._strategy = make_strategy(strategy_name, seed=seed)

    async def decide(self, state: ScientificState) -> ScientificDecision:
        # Budget is a hard ceiling: stopping outranks even failure recovery.
        decision = check_stopping(state) or handle_failures(
            state, ISING_RETRY_ADJUSTMENT, ISING_RETRY_REASON
        )
        if decision is not None:
            return decision
        temperature = float(self._strategy.propose(state.acquisition_state()))
        temperature = min(max(temperature, state.temperature_min), state.temperature_max)
        rationale = {
            "random": "Baseline: uniformly random temperature selection.",
            "grid": "Baseline: bisect the largest unmeasured temperature gap.",
            "uncertainty": "Measure where the bootstrap surrogate ensemble disagrees most.",
        }[self.name]
        return ScientificDecision(
            hypothesis=f"Measuring T={temperature:.3f} refines the susceptibility curve. "
            + rationale,
            evidence=[
                f"{len(state.measurements)} completed measurements",
                model_summary_text(state),
            ],
            uncertainty=model_summary_text(state),
            action_type=ActionType.RUN_MONTE_CARLO,
            temperatures=[temperature],
            expected_information_gain=rationale,
        )
