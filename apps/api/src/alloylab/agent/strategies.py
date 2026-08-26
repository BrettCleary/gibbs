"""Deciders: map a ScientificState to a structured ScientificDecision.

Heuristic deciders wrap the alloyscience baseline strategies (random / grid /
uncertainty) and share the same failure-recovery policy so the benchmark
compares acquisition quality, not bookkeeping. The LLM decider lives in
`llm.py` and satisfies the same protocol.
"""

from __future__ import annotations

import zlib
from typing import Protocol

from alloyscience.benchmark import make_strategy

from .decisions import ActionType, ScientificDecision
from .state import ScientificState


class Decider(Protocol):
    name: str

    async def decide(self, state: ScientificState) -> ScientificDecision: ...


def stable_seed(campaign_id: str) -> int:
    return zlib.crc32(campaign_id.encode())


def handle_failures(state: ScientificState) -> ScientificDecision | None:
    """Shared failure-recovery policy: retry once with more equilibration, then abandon."""
    if not state.unresolved_failures:
        return None
    failure = state.unresolved_failures[0]
    if failure.is_retry:
        return ScientificDecision(
            hypothesis=f"Calculation {failure.calculation_id} at T={failure.temperature:.3f} "
            "failed again after a retry with adjusted settings.",
            evidence=[f"failure category: {failure.category}", "retry also failed"],
            uncertainty="This temperature remains unmeasured; nearby measurements must compensate.",
            action_type=ActionType.ABANDON_CALCULATION,
            retry_calculation_id=failure.calculation_id,
            expected_information_gain="Avoid spending further budget on a pathological run.",
        )
    return ScientificDecision(
        hypothesis=f"Run at T={failure.temperature:.3f} failed with {failure.category}; "
        "a longer equilibration should converge.",
        evidence=[f"failure category: {failure.category}", str(failure.metadata)],
        uncertainty="The failed temperature carries no information until re-run.",
        action_type=ActionType.RETRY_CALCULATION,
        retry_calculation_id=failure.calculation_id,
        adjusted_parameters={"n_equilibration_sweeps_factor": 3.0},
        reason_for_change="Tripled equilibration sweeps to address non-equilibrated chain.",
        expected_information_gain="Recovers the planned measurement at the failed temperature.",
    )


def check_stopping(state: ScientificState) -> ScientificDecision | None:
    if state.budget_remaining <= 0:
        return ScientificDecision(
            hypothesis="The simulation budget is exhausted.",
            evidence=[f"{state.budget_used}/{state.budget_total} simulations consumed"],
            uncertainty=_tc_summary(state),
            action_type=ActionType.FINISH_CAMPAIGN,
            stopping_rationale="Simulation budget exhausted; reporting best current estimate.",
        )
    if (
        state.target_uncertainty is not None
        and state.latest_model is not None
        and state.latest_model.tc_std is not None
        and state.latest_model.tc_std < state.target_uncertainty
    ):
        return ScientificDecision(
            hypothesis="The critical-temperature estimate has reached the requested precision.",
            evidence=[
                f"Tc = {state.latest_model.tc_mean:.4f} ± {state.latest_model.tc_std:.4f}",
                f"target uncertainty: {state.target_uncertainty}",
            ],
            uncertainty=_tc_summary(state),
            action_type=ActionType.FINISH_CAMPAIGN,
            stopping_rationale=(
                f"Ensemble Tc std {state.latest_model.tc_std:.4f} is below the "
                f"target {state.target_uncertainty}; further runs have low expected value."
            ),
        )
    return None


def _tc_summary(state: ScientificState) -> str:
    if state.latest_model and state.latest_model.tc_mean is not None:
        return (
            f"Current estimate Tc = {state.latest_model.tc_mean:.4f} "
            f"± {state.latest_model.tc_std:.4f} (surrogate v{state.latest_model.version})"
        )
    return "No surrogate model fitted yet."


class HeuristicDecider:
    """Wraps a baseline acquisition strategy in the decision schema."""

    def __init__(self, strategy_name: str, seed: int = 0):
        self.name = strategy_name
        self._strategy = make_strategy(strategy_name, seed=seed)

    async def decide(self, state: ScientificState) -> ScientificDecision:
        decision = handle_failures(state) or check_stopping(state)
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
                _tc_summary(state),
            ],
            uncertainty=_tc_summary(state),
            action_type=ActionType.RUN_MONTE_CARLO,
            temperatures=[temperature],
            expected_information_gain=rationale,
        )


def make_decider(strategy_name: str, campaign_id: str, model: str | None = None) -> Decider:
    if strategy_name == "agent":
        from .llm import LLMDecider

        return LLMDecider(model=model)
    return HeuristicDecider(strategy_name, seed=stable_seed(campaign_id))
