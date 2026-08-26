import numpy as np
import pytest

from alloyscience.fcc import HiddenFccCE
from alloyscience.phase import (
    PhaseAcquisitionState,
    SliceMeasurements,
    estimate_slice_boundary,
    phase_system,
    propose_phase_point,
    run_phase_point,
    run_phase_benchmark,
)


@pytest.fixture(scope="module")
def system():
    return phase_system()


@pytest.fixture(scope="module")
def hidden(system):
    return HiddenFccCE.random(system.n_parameters, seed=1)


def test_phase_system_is_mc_safe(system):
    # 4x4x4 primitive supercell half-box must exceed the pair cutoff.
    half_box = 4 * system.a / np.sqrt(2.0) / 2.0
    assert half_box > max(system.cutoffs)


def test_run_phase_point_observables(system, hidden):
    p = run_phase_point(
        system, hidden.ecis, x=0.5, temperature=800.0, n_trial_steps=6000, seed=0
    )
    assert p.n_sites == 64
    assert p.heat_capacity >= 0
    assert p.heat_capacity_err >= 0
    assert -1.0 <= p.sro <= 1.0
    assert p.provenance["heat_capacity_units"] == "k_B per atom"


def test_low_t_ordered_high_t_disordered(system, hidden):
    cold = run_phase_point(
        system, hidden.ecis, x=0.5, temperature=300.0, n_trial_steps=12000, seed=1
    )
    hot = run_phase_point(
        system, hidden.ecis, x=0.5, temperature=50_000.0, n_trial_steps=12000, seed=1
    )
    assert cold.sro < -0.15  # unlike-neighbour order
    assert abs(hot.sro) < 0.1  # random solution
    assert cold.mean_energy_per_site < hot.mean_energy_per_site


def test_run_phase_point_validation(system, hidden):
    with pytest.raises(ValueError):
        run_phase_point(system, hidden.ecis, x=0.0, temperature=500.0)
    with pytest.raises(ValueError):
        run_phase_point(system, hidden.ecis, x=0.5, temperature=-1.0)


def test_estimate_slice_boundary_needs_points():
    data = SliceMeasurements(x=0.5, temperatures=[500.0], heat_capacities=[1.0],
                             heat_capacity_errs=[0.1])
    assert estimate_slice_boundary(data, 300, 2400) is None


def test_boundary_peak_recovery():
    # Synthetic C(T) with a peak at 900 K.
    t = np.linspace(300, 2400, 12)
    c = np.exp(-((t - 900.0) ** 2) / (2 * 250.0**2)) * 2.0 + 0.05
    data = SliceMeasurements(
        x=0.5,
        temperatures=list(t),
        heat_capacities=list(c),
        heat_capacity_errs=[0.02] * len(t),
    )
    est = estimate_slice_boundary(data, 300, 2400, seed=0)
    assert est is not None
    assert est.mean == pytest.approx(900.0, abs=120.0)


def test_propose_phase_point_strategies():
    rng = np.random.default_rng(0)
    state = PhaseAcquisitionState(
        t_min=300, t_max=2400,
        slices=[SliceMeasurements(x=0.25), SliceMeasurements(x=0.5)],
    )
    i, t = propose_phase_point(state, "grid", rng)
    assert i == 0 and t == 300.0
    state.slices[0].temperatures.append(t)
    state.slices[0].heat_capacities.append(1.0)
    state.slices[0].heat_capacity_errs.append(0.1)
    i2, _ = propose_phase_point(state, "grid", rng)
    assert i2 == 1  # least-measured slice next
    # uncertainty bootstraps like grid until every slice has 3 points
    i3, _ = propose_phase_point(state, "uncertainty", rng)
    assert i3 == 1
    i4, t4 = propose_phase_point(state, "random", rng)
    assert 0 <= i4 <= 1 and 300 <= t4 <= 2400
    with pytest.raises(ValueError):
        propose_phase_point(state, "nope", rng)


def test_run_phase_benchmark_scores_boundary_error():
    result = run_phase_benchmark(
        "grid", budget=12, seed=7,
        slices=(0.5,), t_min=300.0, t_max=2400.0, n_trial_steps=5000,
    )
    assert result.problem == "phase"
    assert len(result.history) == 12
    assert result.tc_estimate[0] is not None
    assert 300.0 <= result.tc_estimate[0] <= 2400.0
    assert result.boundary_error >= 0
