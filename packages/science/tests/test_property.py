import numpy as np
import pytest

from alloyscience.property import (
    HiddenBulkModulusModel,
    compute_property_ground_truth,
    rank_candidates,
    run_property_benchmark,
)
from alloyscience.property.benchmark import property_pool


def test_bulk_modulus_model_physics():
    m = HiddenBulkModulusModel()
    assert m.bulk_modulus(0.0, 0.0) == pytest.approx(180.0)
    assert m.bulk_modulus(1.0, 0.0) == pytest.approx(76.0)
    # Ordering stiffens; positive formation energy gives no bonus.
    assert m.bulk_modulus(0.5, -0.2) > m.bulk_modulus(0.5, 0.0)
    assert m.bulk_modulus(0.5, +0.2) == pytest.approx(m.bulk_modulus(0.5, 0.0))
    again = HiddenBulkModulusModel.from_dict(HiddenBulkModulusModel.random(3).to_dict())
    assert again == HiddenBulkModulusModel.random(3)


def test_ground_truth_best_is_stable_intermetallic():
    truth = compute_property_ground_truth(seed=1, max_size=4)
    assert truth.best_label in truth.stable_labels
    i = truth.labels.index(truth.best_label)
    assert 0.0 < truth.x[i] < 1.0
    assert truth.best_bulk_modulus == pytest.approx(truth.bulk_modulus[i])


def test_rank_candidates_prefers_stable_high_b_and_penalises_disordered():
    ranked = rank_candidates(
        labels=["a", "b", "c", "d"], x=[0.25, 0.5, 0.75, 0.0],
        e_form=[-0.3, -0.2, -0.1, 0.0], e_form_std=[0.0] * 4,
        e_above_hull=[0.0, 0.0, 0.05, 0.0],
        bulk_modulus=[150.0, 200.0, 300.0, 180.0], bulk_modulus_std=[0.0] * 4,
        measured=[True] * 4, stable_tol=1e-6,
        verification_by_x={0.5: "disordered", 0.25: "ordered"},
    )
    labels = [c.label for c in ranked]
    assert labels[0] == "d" or labels[0] == "a"  # endpoints rank by B as references too
    # b (stiffest stable) is penalised for disordering at threshold; c is unstable.
    assert ranked[-1].label == "c"
    b = next(c for c in ranked if c.label == "b")
    assert b.stability_at_threshold == "disordered" and b.score < 0


@pytest.mark.parametrize("strategy", ["random", "coverage", "uncertainty", "property"])
def test_run_property_benchmark(strategy):
    r = run_property_benchmark(strategy, budget=10, seed=2, max_size=4)
    assert r.problem == "property"
    assert len(r.queried_labels) == 10
    assert r.regret_gpa >= -1e-6
    if r.recommended_label:
        assert r.recommended_true_b is not None


def test_property_strategy_finds_best_with_full_budget():
    _, pool = property_pool(4)
    r = run_property_benchmark("property", budget=len(pool), seed=2, max_size=4)
    assert r.recommended_truly_stable
    assert r.regret_gpa < 5.0
