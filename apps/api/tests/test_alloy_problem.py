import pytest

from alloylab.agent.decisions import ActionType, ScientificDecision
from alloylab.problems.alloy import (
    AlloyHeuristicDecider,
    AlloyProblem,
    AlloyState,
    PoolPrediction,
)


def _state(**overrides) -> AlloyState:
    predictions = [
        PoolPrediction(label="s000-1x1", x=0.0, measured=True),
        PoolPrediction(label="s001-1x1", x=1.0, measured=True),
        PoolPrediction(label="s002-1x2", x=0.5, e_form_mean=-0.5, e_form_std=0.2),
        PoolPrediction(label="s003-2x2", x=0.25, e_form_mean=-0.1, e_form_std=0.05),
    ]
    base = dict(
        campaign_id="c1",
        objective="find stable structures",
        strategy="uncertainty",
        budget_total=10,
        budget_used=2,
        budget_remaining=8,
        target_uncertainty=None,
        unresolved_failures=[],
        latest_model=None,
        composition_min=0.0,
        composition_max=1.0,
        n_structures=4,
        endpoints_measured=True,
        pure_a_label="s000-1x1",
        pure_b_label="s001-1x1",
        measurements=[],
        pool_predictions=predictions,
        predicted_stable=[],
        unmeasured_labels=["s002-1x2", "s003-2x2"],
        suggested_uncertainty_label="s002-1x2",
        suggested_coverage_label="s003-2x2",
    )
    base.update(overrides)
    return AlloyState(**base)


async def test_endpoints_bootstrap_first():
    decider = AlloyHeuristicDecider("uncertainty")
    state = _state(
        endpoints_measured=False,
        unmeasured_labels=["s000-1x1", "s001-1x1", "s002-1x2", "s003-2x2"],
    )
    decision = await decider.decide(state)
    assert decision.action_type == ActionType.RUN_STRUCTURE_ENERGY
    assert decision.structure_labels == ["s000-1x1", "s001-1x1"]


async def test_uncertainty_decider_picks_most_uncertain():
    decider = AlloyHeuristicDecider("uncertainty")
    decision = await decider.decide(_state())
    assert decision.structure_labels == ["s002-1x2"]


async def test_coverage_decider_uses_coverage_suggestion():
    decider = AlloyHeuristicDecider("grid")
    decision = await decider.decide(_state())
    assert decision.structure_labels == ["s003-2x2"]


async def test_pool_exhausted_finishes():
    decider = AlloyHeuristicDecider("random")
    decision = await decider.decide(_state(unmeasured_labels=[]))
    assert decision.action_type == ActionType.FINISH_CAMPAIGN


def test_validate_drops_measured_and_unknown_labels():
    problem = AlloyProblem()
    d = ScientificDecision(
        hypothesis="h",
        action_type=ActionType.RUN_STRUCTURE_ENERGY,
        structure_labels=["s000-1x1", "s002-1x2", "nope", "s002-1x2"],
    )
    cleaned = problem.validate(_state(), d)
    assert cleaned.structure_labels == ["s002-1x2"]


def test_validate_repairs_empty_with_suggestion():
    problem = AlloyProblem()
    d = ScientificDecision(hypothesis="h", action_type=ActionType.RUN_STRUCTURE_ENERGY)
    cleaned = problem.validate(_state(), d)
    assert cleaned.structure_labels == ["s002-1x2"]


def test_validate_errors_when_nothing_left():
    problem = AlloyProblem()
    d = ScientificDecision(hypothesis="h", action_type=ActionType.RUN_STRUCTURE_ENERGY)
    with pytest.raises(ValueError):
        problem.validate(
            _state(
                unmeasured_labels=[],
                suggested_uncertainty_label=None,
                suggested_coverage_label=None,
            ),
            d,
        )
