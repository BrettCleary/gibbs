import numpy as np
import pytest

from alloyscience.alloy import (
    ClusterExpansionSurrogate,
    HiddenPairHamiltonian,
    StructureOracle,
    compute_alloy_ground_truth,
    enumerate_structures,
    structure_features,
)
from alloyscience.benchmark import (
    AlloyAcquisitionState,
    predicted_hull_from_state,
    propose_structure,
    run_alloy_benchmark,
)
from alloyscience.benchmark.harness import SimulationFailure


def _pool():
    return enumerate_structures()


def _find(pool, predicate):
    return next(s for s in pool if predicate(s))


def test_features_of_known_structures():
    # Pure B: all correlations 1.
    assert structure_features(np.ones((2, 2))) == (1.0, 1.0, 1.0)
    # Checkerboard: unlike NN (-1), like NNN (+1), zero point.
    checker = np.array([[1, -1], [-1, 1]])
    assert structure_features(checker) == (0.0, -1.0, 1.0)


def test_enumeration_contains_endpoints_and_checkerboard():
    pool = _pool()
    labels_x = {round(s.x, 4) for s in pool}
    assert 0.0 in labels_x and 1.0 in labels_x
    checker = [s for s in pool if s.features == (0.0, -1.0, 1.0)]
    assert len(checker) == 1  # deduplicated across tile shapes
    # Feature-distinct pool of a sensible size.
    assert 30 <= len(pool) <= 200


def test_checkerboard_formation_energy_is_minus_4_j1():
    pool = _pool()
    h = HiddenPairHamiltonian(j1=1.0, j2=0.3)
    checker = _find(pool, lambda s: s.features == (0.0, -1.0, 1.0))
    assert h.formation_energy(checker) == pytest.approx(-4.0 * h.j1)
    # Pure endpoints have zero formation energy by construction.
    pure_a = _find(pool, lambda s: s.x == 0.0)
    assert h.formation_energy(pure_a) == pytest.approx(0.0)


def test_ground_truth_stable_set_includes_checkerboard():
    pool = _pool()
    h = HiddenPairHamiltonian(j1=1.0, j2=0.0)
    truth = compute_alloy_ground_truth(h, pool)
    checker = _find(pool, lambda s: s.features == (0.0, -1.0, 1.0))
    assert checker.label in truth.stable_labels


def test_oracle_noise_determinism_and_failure():
    pool = _pool()
    h = HiddenPairHamiltonian(j1=1.0, j2=0.1, noise_sigma=0.02)
    oracle = StructureOracle(h, seed=5)
    s = pool[3]
    assert oracle.evaluate(s, query_seed=7) == oracle.evaluate(s, query_seed=7)
    flaky = StructureOracle(h, failure_rate=1.0, seed=5)
    with pytest.raises(SimulationFailure) as exc:
        flaky.evaluate(s, query_seed=1)
    assert exc.value.category == "SCF_NOT_CONVERGED"
    # Retries never re-inject.
    assert isinstance(flaky.evaluate(s, query_seed=1, is_retry=True), float)


def test_cluster_expansion_recovers_hidden_hamiltonian():
    pool = _pool()
    h = HiddenPairHamiltonian(j1=0.9, j2=-0.2, noise_sigma=0.0)
    train = pool[:: max(len(pool) // 12, 1)]
    features = np.stack([s.feature_vector() for s in train])
    energies = np.array([h.energy_per_site(s) for s in train])
    ce = ClusterExpansionSurrogate(features, energies, seed=0)
    coefs = ce.coefficient_summary()
    assert coefs["J_nn"]["mean"] == pytest.approx(2 * h.j1, abs=1e-6)
    assert coefs["J_nnn"]["mean"] == pytest.approx(2 * h.j2, abs=1e-6)
    mean, std = ce.predict(np.stack([s.feature_vector() for s in pool]))
    truth_e = np.array([h.energy_per_site(s) for s in pool])
    assert np.allclose(mean, truth_e, atol=1e-6)


def test_cluster_expansion_requires_min_points():
    with pytest.raises(ValueError):
        ClusterExpansionSurrogate(np.ones((3, 4)), np.ones(3))


def test_propose_structure_strategies():
    pool = _pool()
    rng = np.random.default_rng(0)
    state = AlloyAcquisitionState(pool=pool)
    i = propose_structure(state, "random", rng)
    assert 0 <= i < len(pool)
    state.measured_energies[i] = 0.0
    j = propose_structure(state, "coverage", rng)
    assert j != i
    with pytest.raises(ValueError):
        propose_structure(state, "nope", rng)


def test_predicted_hull_requires_endpoints():
    pool = _pool()
    state = AlloyAcquisitionState(pool=pool)
    state.measured_energies[5] = -1.0
    with pytest.raises(ValueError):
        predicted_hull_from_state(state)


@pytest.mark.parametrize("strategy", ["random", "coverage", "uncertainty"])
def test_run_alloy_benchmark(strategy):
    result = run_alloy_benchmark(strategy, budget=10, seed=3)
    assert result.strategy == strategy
    assert len(result.queried_labels) == 10
    assert result.score.hull_rmse >= 0
    assert result.score.n_true_stable >= 2  # at least the two endpoints


def test_full_budget_noise_free_recovers_exact_hull():
    pool = _pool()
    h = HiddenPairHamiltonian(j1=0.8, j2=0.5, noise_sigma=0.0)
    result = run_alloy_benchmark(
        "uncertainty", budget=len(pool), seed=1, hamiltonian=h, pool=pool
    )
    assert result.score.hull_rmse < 1e-9
    assert not result.score.missed_stable
    assert not result.score.false_stable


def test_full_budget_noisy_hull_error_is_small():
    # With measurement noise, degenerate hull ties may be missed — but the
    # hull itself should still be accurate to roughly the noise level.
    pool = _pool()
    result = run_alloy_benchmark("uncertainty", budget=len(pool), seed=1, pool=pool)
    assert result.score.hull_rmse < 0.05
    assert not result.score.false_stable
