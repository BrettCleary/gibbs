import numpy as np
import pytest

from alloyscience.alloy.cluster_expansion import ClusterExpansionSurrogate
from alloyscience.alloy.ground_truth import compute_ground_truth_from_energy_fn
from alloyscience.benchmark import run_fcc_benchmark
from alloyscience.errors import SimulationFailure
from alloyscience.fcc import FccSystem, HiddenFccCE, run_canonical_mc
from alloyscience.fcc.system import cached_system_and_pool


@pytest.fixture(scope="module")
def system_and_pool():
    return cached_system_and_pool(max_size=4)


def test_enumeration_has_endpoints_and_l1_structures(system_and_pool):
    system, pool = system_and_pool
    assert system.n_parameters >= 4  # zerolet, singlet, >= 2 pair orbits
    xs = {s.x for s in pool}
    assert 0.0 in xs and 1.0 in xs
    # L1_2-like composition present (Ni3Al) and L1_0-like (NiAl).
    assert any(abs(s.x - 0.25) < 1e-9 for s in pool)
    assert any(abs(s.x - 0.5) < 1e-9 for s in pool)
    # Cluster vectors are distinct by construction; zerolet element is 1.
    assert all(s.cluster_vector[0] == pytest.approx(1.0) for s in pool)
    cvs = {s.cluster_vector for s in pool}
    assert len(cvs) == len(pool)


def test_structures_are_self_contained(system_and_pool):
    _, pool = system_and_pool
    s = pool[5]
    assert len(s.positions) == s.n_sites
    assert len(s.atomic_numbers) == s.n_sites
    assert len(s.cell) == 3
    assert set(s.atomic_numbers) <= {13, 28}  # Al, Ni


def test_hidden_ce_orders_and_endpoints_cancel(system_and_pool):
    system, pool = system_and_pool
    hidden = HiddenFccCE.random(system.n_parameters, seed=1)
    assert hidden.ecis[2] > 0  # NN pair favours ordering
    truth = compute_ground_truth_from_energy_fn(list(pool), hidden.energy_per_site)
    e_by_label = dict(zip(truth.labels, truth.e_form))
    pure = [s for s in pool if s.x in (0.0, 1.0)]
    for s in pure:
        assert e_by_label[s.label] == pytest.approx(0.0, abs=1e-12)
    # Ordering physics: at least one intermediate structure below zero.
    assert min(truth.e_form) < -0.01
    assert len(truth.stable_labels) > 2


def test_hidden_ce_roundtrip(system_and_pool):
    system, _ = system_and_pool
    hidden = HiddenFccCE.random(system.n_parameters, seed=3)
    again = HiddenFccCE.from_dict(hidden.to_dict())
    assert again == hidden


def test_ce_surrogate_recovers_hidden_ecis(system_and_pool):
    system, pool = system_and_pool
    hidden = HiddenFccCE.random(system.n_parameters, seed=2, noise_sigma=0.0)
    train = list(pool)[:: max(len(pool) // 15, 1)]
    features = np.stack([s.feature_vector() for s in train])
    energies = np.array([hidden.energy_per_site(s) for s in train])
    ce = ClusterExpansionSurrogate(features, energies, seed=0, ridge=1e-10)
    mean, _ = ce.predict(np.stack([s.feature_vector() for s in pool]))
    truth = np.array([hidden.energy_per_site(s) for s in pool])
    assert np.allclose(mean, truth, atol=1e-5)
    coefs = ce.coefficient_summary()
    assert len(coefs) == system.n_parameters  # no coefficient dropped for k > 4


@pytest.mark.parametrize("strategy", ["random", "coverage", "uncertainty"])
def test_run_fcc_benchmark(strategy):
    result = run_fcc_benchmark(strategy, budget=12, seed=1, max_size=4)
    assert result.problem == "fcc"
    assert len(result.queried_labels) == 12
    assert result.score.hull_rmse >= 0
    assert "ecis" in result.hidden_params


def test_canonical_mc_orders_at_low_temperature(system_and_pool):
    system, pool = system_and_pool
    hidden = HiddenFccCE.random(system.n_parameters, seed=1, noise_sigma=0.0)
    cold = run_canonical_mc(
        system, hidden.ecis, x=0.5, temperature=100.0,
        supercell_repeat=3, n_trial_steps=6000, seed=0,
    )
    hot = run_canonical_mc(
        system, hidden.ecis, x=0.5, temperature=100_000.0,
        supercell_repeat=3, n_trial_steps=6000, seed=0,
    )
    assert cold.n_sites == 27
    # Low temperature finds lower energy and unlike-neighbour order (alpha < 0).
    assert cold.mean_energy_per_site < hot.mean_energy_per_site
    assert cold.sro_warren_cowley < 0
    assert abs(hot.sro_warren_cowley) < abs(cold.sro_warren_cowley) + 0.15


def test_oracle_failure_injection_for_fcc(system_and_pool):
    from alloyscience.alloy.hamiltonian import StructureOracle

    system, pool = system_and_pool
    hidden = HiddenFccCE.random(system.n_parameters, seed=4)
    flaky = StructureOracle(hidden, failure_rate=1.0, seed=0)
    with pytest.raises(SimulationFailure):
        flaky.evaluate(pool[3], query_seed=0)
    assert isinstance(flaky.evaluate(pool[3], query_seed=0, is_retry=True), float)
