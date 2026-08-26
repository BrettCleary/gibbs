import pytest

from alloyscience.benchmark import (
    AcquisitionState,
    FlakyOracle,
    GroundTruth,
    IsingOracle,
    SimulationFailure,
    make_strategy,
    run_benchmark,
)


def _tiny_ground_truth():
    # Precomputed-shape ground truth to keep the test fast; the harness only
    # needs the range and a tc value to score against.
    return GroundTruth(
        lattice_size=8,
        t_min=1.5,
        t_max=3.5,
        tc=2.35,
        temperatures=[],
        susceptibility=[],
    )


def test_make_strategy_names():
    for name in ("random", "grid", "uncertainty"):
        assert make_strategy(name).name == name
    with pytest.raises(ValueError):
        make_strategy("nope")


def test_grid_strategy_covers_range():
    s = make_strategy("grid")
    state = AcquisitionState(t_min=1.0, t_max=3.0)
    picks = []
    for _ in range(5):
        t = s.propose(state)
        picks.append(t)
        state.measured_temperatures.append(t)
        state.measured_values.append(1.0)
        state.measured_errors.append(0.1)
    assert picks[0] == 1.0
    assert picks[1] == 3.0
    assert picks[2] == pytest.approx(2.0)
    assert len(set(round(p, 6) for p in picks)) == 5


def test_run_benchmark_produces_scored_result():
    gt = _tiny_ground_truth()
    oracle = IsingOracle(lattice_size=8, n_equilibration_sweeps=100, n_measurement_sweeps=300)
    result = run_benchmark(make_strategy("grid"), budget=6, ground_truth=gt, oracle=oracle, seed=1)
    assert result.budget == 6
    assert len(result.history) == 6
    assert result.tc_error >= 0
    assert gt.t_min <= result.tc_estimate <= gt.t_max


def test_flaky_oracle_raises_categorised_failure():
    oracle = FlakyOracle(
        IsingOracle(lattice_size=8, n_equilibration_sweeps=10, n_measurement_sweeps=20),
        failure_rate=1.0,
        seed=0,
    )
    with pytest.raises(SimulationFailure) as exc:
        oracle.evaluate(2.0, seed=0)
    assert exc.value.category == "MC_NOT_EQUILIBRATED"
