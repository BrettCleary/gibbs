import pytest

from gibbs.agent.decisions import ActionType, ScientificDecision
from gibbs.agent.state import FailureRecord, Measurement, ScientificState
from gibbs.agent.strategies import (
    HeuristicDecider,
    ISING_RETRY_ADJUSTMENT,
    ISING_RETRY_REASON,
    handle_failures,
)
from gibbs.problems.alloy import AlloyHeuristicDecider
from gibbs.problems.phase import PhaseHeuristicDecider
from gibbs.problems.property import PropertyHeuristicDecider
from gibbs.problems.ising import IsingProblem


def _state(**overrides) -> ScientificState:
    base = dict(
        campaign_id="c1",
        objective="find Tc",
        strategy="grid",
        temperature_min=1.5,
        temperature_max=3.5,
        lattice_size=8,
        budget_total=10,
        budget_used=0,
        budget_remaining=10,
        target_uncertainty=None,
        measurements=[],
        unresolved_failures=[],
        latest_model=None,
        suggested_uncertainty_temperature=None,
    )
    base.update(overrides)
    return ScientificState(**base)


def test_validate_clamps_out_of_range_temperatures():
    d = ScientificDecision(
        hypothesis="h",
        action_type=ActionType.RUN_MONTE_CARLO,
        temperatures=[0.1, 9.0, 2.0],
    )
    cleaned = IsingProblem().validate(_state(), d)
    assert cleaned.temperatures == [1.5, 3.5, 2.0]


def test_validate_caps_batch_and_budget():
    d = ScientificDecision(
        hypothesis="h",
        action_type=ActionType.RUN_MONTE_CARLO,
        temperatures=[2.0, 2.1, 2.2, 2.3],
    )
    cleaned = IsingProblem().validate(_state(budget_remaining=2), d)
    assert len(cleaned.temperatures) == 2


def test_validate_repairs_empty_proposal():
    d = ScientificDecision(hypothesis="h", action_type=ActionType.RUN_MONTE_CARLO)
    cleaned = IsingProblem().validate(_state(suggested_uncertainty_temperature=2.7), d)
    assert cleaned.temperatures == [2.7]


def test_validate_rejects_unknown_retry_target():
    d = ScientificDecision(
        hypothesis="h",
        action_type=ActionType.RETRY_CALCULATION,
        retry_calculation_id="missing",
    )
    with pytest.raises(ValueError):
        IsingProblem().validate(_state(), d)


def test_failure_policy_retries_then_abandons():
    failure = FailureRecord(
        calculation_id="f1",
        description="T=2.200",
        category="MC_NOT_EQUILIBRATED",
        metadata={},
        is_retry=False,
    )
    d = handle_failures(
        _state(unresolved_failures=[failure]), ISING_RETRY_ADJUSTMENT, ISING_RETRY_REASON
    )
    assert d is not None and d.action_type == ActionType.RETRY_CALCULATION
    assert d.retry_calculation_id == "f1"
    assert d.adjusted_parameters == ISING_RETRY_ADJUSTMENT

    failed_retry = failure.model_copy(update={"is_retry": True})
    d2 = handle_failures(
        _state(unresolved_failures=[failed_retry]), ISING_RETRY_ADJUSTMENT, ISING_RETRY_REASON
    )
    assert d2 is not None and d2.action_type == ActionType.ABANDON_CALCULATION


async def test_heuristic_decider_finishes_on_exhausted_budget():
    decider = HeuristicDecider("grid")
    decision = await decider.decide(_state(budget_used=10, budget_remaining=0))
    assert decision.action_type == ActionType.FINISH_CAMPAIGN
    assert decision.stopping_rationale


async def test_heuristic_decider_proposes_measurement():
    decider = HeuristicDecider("grid")
    m = [
        Measurement(
            calculation_id=f"m{i}", temperature=t, susceptibility=1.0, susceptibility_err=0.1
        )
        for i, t in enumerate([1.5, 3.5])
    ]
    decision = await decider.decide(_state(measurements=m, budget_used=2, budget_remaining=8))
    assert decision.action_type == ActionType.RUN_MONTE_CARLO
    assert decision.temperatures == [pytest.approx(2.5)]


@pytest.mark.parametrize(
    "cls", [HeuristicDecider, AlloyHeuristicDecider, PhaseHeuristicDecider, PropertyHeuristicDecider]
)
def test_unknown_strategy_is_rejected(cls):
    # Without this, a typo'd name fell through to the uncertainty branch and the
    # decision text claimed an acquisition rule that had not been used.
    with pytest.raises(ValueError, match="unknown"):
        cls("uncertainy")
    assert cls("uncertainty").kind == "heuristic"


async def test_heuristic_decisions_are_marked_as_computed():
    """Baselines emit the same schema as the LLM scientist; `source` is what keeps
    a templated argmax from being displayed as model reasoning."""
    decider = HeuristicDecider("grid")
    decision = await decider.decide(_state(budget_used=2, budget_remaining=8))
    assert decision.source == "code"
    assert ScientificDecision(hypothesis="h", action_type=ActionType.FINISH_CAMPAIGN).source == "code"
