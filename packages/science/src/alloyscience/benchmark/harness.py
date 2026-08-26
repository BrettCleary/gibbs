"""Benchmark harness: does a strategy find the critical region efficiently?

Ground truth for a given lattice size is computed once with a large compute
budget (dense temperature grid, long runs); strategies then get a small query
budget and are scored on the error of their susceptibility-peak estimate
against that ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np

from ..ising import IsingSimulator
from ..surrogate import ResponseSurrogate
from .strategies import AcquisitionState, Strategy


from ..errors import SimulationFailure  # noqa: E402  (re-export for compatibility)


class IsingOracle:
    """The 'expensive experiment': one Monte Carlo run at a chosen temperature."""

    def __init__(
        self,
        lattice_size: int = 24,
        n_equilibration_sweeps: int = 800,
        n_measurement_sweeps: int = 2000,
    ):
        self.simulator = IsingSimulator(lattice_size)
        self.n_equilibration_sweeps = n_equilibration_sweeps
        self.n_measurement_sweeps = n_measurement_sweeps

    def evaluate(self, temperature: float, seed: int = 0):
        return self.simulator.run(
            temperature,
            n_equilibration_sweeps=self.n_equilibration_sweeps,
            n_measurement_sweeps=self.n_measurement_sweeps,
            seed=seed,
        )


class FlakyOracle:
    """Wraps an oracle, deterministically injecting failures for recovery tests."""

    def __init__(self, oracle: IsingOracle, failure_rate: float = 0.15, seed: int = 0):
        self.oracle = oracle
        self.failure_rate = failure_rate
        self._rng = np.random.default_rng(seed)

    def evaluate(self, temperature: float, seed: int = 0):
        if self._rng.random() < self.failure_rate:
            raise SimulationFailure(
                category="MC_NOT_EQUILIBRATED",
                message="injected failure: Monte Carlo chain flagged as not equilibrated",
                metadata={"temperature": temperature, "seed": seed},
            )
        return self.oracle.evaluate(temperature, seed=seed)


@dataclass(frozen=True)
class GroundTruth:
    lattice_size: int
    t_min: float
    t_max: float
    tc: float
    temperatures: list[float]
    susceptibility: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


_GROUND_TRUTH_CACHE: dict[tuple, GroundTruth] = {}


def compute_ground_truth(
    lattice_size: int = 24,
    t_min: float = 1.5,
    t_max: float = 3.5,
    n_grid: int = 33,
    n_equilibration_sweeps: int = 1500,
    n_measurement_sweeps: int = 6000,
    seed: int = 12345,
) -> GroundTruth:
    """High-budget dense scan; the pseudo-critical peak is the ground truth."""
    key = (lattice_size, t_min, t_max, n_grid, n_equilibration_sweeps, n_measurement_sweeps, seed)
    if key in _GROUND_TRUTH_CACHE:
        return _GROUND_TRUTH_CACHE[key]
    sim = IsingSimulator(lattice_size)
    temps = np.linspace(t_min, t_max, n_grid)
    chis, errs = [], []
    for i, t in enumerate(temps):
        r = sim.run(
            float(t),
            n_equilibration_sweeps=n_equilibration_sweeps,
            n_measurement_sweeps=n_measurement_sweeps,
            seed=seed + i,
        )
        chis.append(r.susceptibility)
        errs.append(r.susceptibility_err)
    surrogate = ResponseSurrogate(temps, chis, errs, seed=seed)
    tc = surrogate.estimate_peak(t_min, t_max).mean
    gt = GroundTruth(
        lattice_size=lattice_size,
        t_min=t_min,
        t_max=t_max,
        tc=tc,
        temperatures=[float(t) for t in temps],
        susceptibility=[float(c) for c in chis],
    )
    _GROUND_TRUTH_CACHE[key] = gt
    return gt


@dataclass(frozen=True)
class BenchmarkRecord:
    query_index: int
    temperature: float
    susceptibility: float
    susceptibility_err: float
    tc_estimate: float | None
    tc_std: float | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class BenchmarkRunResult:
    strategy: str
    seed: int
    budget: int
    lattice_size: int
    tc_true: float
    tc_estimate: float
    tc_std: float
    tc_error: float
    history: list[BenchmarkRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def run_benchmark(
    strategy: Strategy,
    budget: int,
    ground_truth: GroundTruth,
    oracle: IsingOracle | None = None,
    seed: int = 0,
) -> BenchmarkRunResult:
    """Run one strategy against the oracle for `budget` queries and score it."""
    if oracle is None:
        oracle = IsingOracle(lattice_size=ground_truth.lattice_size)
    state = AcquisitionState(t_min=ground_truth.t_min, t_max=ground_truth.t_max)
    history: list[BenchmarkRecord] = []

    for i in range(budget):
        state.remaining_budget = budget - i
        temperature = float(np.clip(strategy.propose(state), state.t_min, state.t_max))
        result = oracle.evaluate(temperature, seed=seed * 10_000 + i)
        state.measured_temperatures.append(temperature)
        state.measured_values.append(result.susceptibility)
        state.measured_errors.append(result.susceptibility_err)

        tc_est = tc_std = None
        surrogate = state.surrogate(seed=seed)
        if surrogate is not None:
            est = surrogate.estimate_peak(state.t_min, state.t_max)
            tc_est, tc_std = est.mean, est.std
        history.append(
            BenchmarkRecord(
                query_index=i,
                temperature=temperature,
                susceptibility=result.susceptibility,
                susceptibility_err=result.susceptibility_err,
                tc_estimate=tc_est,
                tc_std=tc_std,
            )
        )

    final = state.surrogate(seed=seed)
    if final is None:
        raise ValueError("budget too small to fit a surrogate (need >= 3 queries)")
    est = final.estimate_peak(state.t_min, state.t_max)
    return BenchmarkRunResult(
        strategy=getattr(strategy, "name", type(strategy).__name__),
        seed=seed,
        budget=budget,
        lattice_size=ground_truth.lattice_size,
        tc_true=ground_truth.tc,
        tc_estimate=est.mean,
        tc_std=est.std,
        tc_error=abs(est.mean - ground_truth.tc),
        history=history,
    )
