"""Phase-boundary estimation and (x, T) acquisition for Milestone 5.

Each composition slice is a one-dimensional peak-location problem — the
heat-capacity peak C(T) marks the order/disorder transition — so the V0
bootstrap-ensemble surrogate is reused per slice: its peak estimate gives
T_c(x) and its ensemble spread gives the boundary uncertainty that drives
acquisition ("investigate uncertain boundaries").
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..benchmark.strategies import AcquisitionState, GridStrategy
from ..surrogate import ResponseSurrogate, TcEstimate

PHASE_STRATEGIES = ("random", "grid", "uncertainty")


@dataclass
class SliceMeasurements:
    x: float
    temperatures: list[float] = field(default_factory=list)
    heat_capacities: list[float] = field(default_factory=list)
    heat_capacity_errs: list[float] = field(default_factory=list)

    def acquisition_state(self, t_min: float, t_max: float) -> AcquisitionState:
        return AcquisitionState(
            t_min=t_min,
            t_max=t_max,
            measured_temperatures=list(self.temperatures),
            measured_values=list(self.heat_capacities),
            measured_errors=list(self.heat_capacity_errs),
        )


def estimate_slice_boundary(
    slice_data: SliceMeasurements, t_min: float, t_max: float, seed: int = 0
) -> TcEstimate | None:
    """T_c(x) from the heat-capacity peak, with bootstrap-ensemble uncertainty."""
    if len(slice_data.temperatures) < ResponseSurrogate.MIN_POINTS:
        return None
    surrogate = ResponseSurrogate(
        slice_data.temperatures,
        slice_data.heat_capacities,
        slice_data.heat_capacity_errs,
        seed=seed,
    )
    return surrogate.estimate_peak(t_min, t_max)


@dataclass
class PhaseAcquisitionState:
    t_min: float
    t_max: float
    slices: list[SliceMeasurements]
    remaining_budget: int = 0

    def boundary_estimates(self, seed: int = 0) -> list[TcEstimate | None]:
        return [
            estimate_slice_boundary(s, self.t_min, self.t_max, seed=seed) for s in self.slices
        ]


def propose_phase_point(
    state: PhaseAcquisitionState, strategy: str, rng: np.random.Generator
) -> tuple[int, float]:
    """(slice index, temperature) for the next canonical MC run."""
    n_slices = len(state.slices)
    if n_slices == 0:
        raise ValueError("no composition slices configured")

    if strategy == "random":
        i = int(rng.integers(0, n_slices))
        return i, float(rng.uniform(state.t_min, state.t_max))

    if strategy == "grid":
        # Round-robin the least-measured slice, then bisect its largest T gap.
        counts = [len(s.temperatures) for s in state.slices]
        i = int(np.argmin(counts))
        t = GridStrategy().propose(state.slices[i].acquisition_state(state.t_min, state.t_max))
        return i, float(t)

    if strategy == "uncertainty":
        # Bootstrap every slice to 3 points first, then chase the largest
        # boundary uncertainty and measure where its surrogate is least sure.
        counts = [len(s.temperatures) for s in state.slices]
        if min(counts) < ResponseSurrogate.MIN_POINTS:
            i = int(np.argmin(counts))
            t = GridStrategy().propose(
                state.slices[i].acquisition_state(state.t_min, state.t_max)
            )
            return i, float(t)
        estimates = state.boundary_estimates(seed=int(rng.integers(0, 2**31)))
        stds = [e.std if e is not None else np.inf for e in estimates]
        i = int(np.argmax(stds))
        surrogate = ResponseSurrogate(
            state.slices[i].temperatures,
            state.slices[i].heat_capacities,
            state.slices[i].heat_capacity_errs,
            seed=int(rng.integers(0, 2**31)),
        )
        # Peak-refinement acquisition (posterior sampling), not raw max-std:
        # edge variance would otherwise dominate and waste the budget.
        t = surrogate.suggest_peak_refinement(
            state.t_min, state.t_max, exclude=state.slices[i].temperatures
        )
        return i, float(t)

    raise ValueError(f"unknown phase strategy {strategy!r}; expected one of {PHASE_STRATEGIES}")
