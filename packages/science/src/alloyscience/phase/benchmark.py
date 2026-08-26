"""Phase-boundary benchmark: does smart (x, T) selection map the phase diagram
with fewer Monte Carlo runs? Scored on the plan's phase-boundary error metric.

Ground truth per seed: a dense, higher-budget C(T) scan per composition slice
on the same hidden cluster expansion, with the same peak estimator.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from functools import lru_cache

import numpy as np

from ..fcc import HiddenFccCE
from .boundary import (
    PhaseAcquisitionState,
    SliceMeasurements,
    estimate_slice_boundary,
    propose_phase_point,
)
from .mc import phase_system, run_phase_point

DEFAULT_SLICES = (0.25, 0.5, 0.75)
DEFAULT_T_MIN = 100.0
DEFAULT_T_MAX = 1200.0


@dataclass(frozen=True)
class PhaseGroundTruth:
    seed: int
    slices: list[float]
    t_min: float
    t_max: float
    tc: list[float]
    ecis: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=16)
def compute_phase_ground_truth(
    seed: int,
    slices: tuple[float, ...] = DEFAULT_SLICES,
    t_min: float = DEFAULT_T_MIN,
    t_max: float = DEFAULT_T_MAX,
    n_grid: int = 11,
    n_trial_steps: int = 40_000,
) -> PhaseGroundTruth:
    system = phase_system()
    hidden = HiddenFccCE.random(system.n_parameters, seed=seed)
    tcs = []
    for x in slices:
        data = SliceMeasurements(x=x)
        for j, t in enumerate(np.linspace(t_min, t_max, n_grid)):
            p = run_phase_point(
                system, hidden.ecis, x=x, temperature=float(t),
                n_trial_steps=n_trial_steps, seed=seed * 1000 + j,
            )
            data.temperatures.append(p.temperature)
            data.heat_capacities.append(p.heat_capacity)
            data.heat_capacity_errs.append(p.heat_capacity_err)
        est = estimate_slice_boundary(data, t_min, t_max, seed=seed)
        tcs.append(est.mean)
    return PhaseGroundTruth(
        seed=seed,
        slices=list(slices),
        t_min=t_min,
        t_max=t_max,
        tc=tcs,
        ecis=list(hidden.ecis),
    )


@dataclass(frozen=True)
class PhaseBenchmarkResult:
    problem: str
    strategy: str
    seed: int
    budget: int
    slices: list[float]
    tc_true: list[float]
    tc_estimate: list[float | None]
    tc_std: list[float | None]
    boundary_error: float  # mean |Tc_est - Tc_true| over slices (K)
    max_boundary_error: float
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def run_phase_benchmark(
    strategy: str,
    budget: int,
    seed: int,
    slices: tuple[float, ...] = DEFAULT_SLICES,
    t_min: float = DEFAULT_T_MIN,
    t_max: float = DEFAULT_T_MAX,
    n_trial_steps: int = 20_000,
) -> PhaseBenchmarkResult:
    truth = compute_phase_ground_truth(seed, slices, t_min, t_max)
    system = phase_system()
    hidden = HiddenFccCE.from_dict({"ecis": truth.ecis, "noise_sigma": 0.0})
    rng = np.random.default_rng(seed)
    state = PhaseAcquisitionState(
        t_min=t_min, t_max=t_max, slices=[SliceMeasurements(x=x) for x in slices]
    )
    history = []
    for q in range(budget):
        state.remaining_budget = budget - q
        i, t = propose_phase_point(state, strategy, rng)
        t = float(np.clip(t, t_min, t_max))
        p = run_phase_point(
            system, hidden.ecis, x=slices[i], temperature=t,
            n_trial_steps=n_trial_steps, seed=seed * 10_000 + q,
        )
        state.slices[i].temperatures.append(p.temperature)
        state.slices[i].heat_capacities.append(p.heat_capacity)
        state.slices[i].heat_capacity_errs.append(p.heat_capacity_err)
        history.append({"query": q, "x": slices[i], "T": t, "C": p.heat_capacity})

    estimates = state.boundary_estimates(seed=seed)
    tc_est = [e.mean if e else None for e in estimates]
    tc_std = [e.std if e else None for e in estimates]
    errors = [
        abs(est - true) if est is not None else (t_max - t_min)
        for est, true in zip(tc_est, truth.tc)
    ]
    return PhaseBenchmarkResult(
        problem="phase",
        strategy=strategy,
        seed=seed,
        budget=budget,
        slices=list(slices),
        tc_true=truth.tc,
        tc_estimate=tc_est,
        tc_std=tc_std,
        boundary_error=float(np.mean(errors)),
        max_boundary_error=float(np.max(errors)),
        history=history,
    )
