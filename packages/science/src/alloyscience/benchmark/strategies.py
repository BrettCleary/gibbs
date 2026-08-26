"""Baseline experiment-selection strategies for the Ising critical-region search.

Each strategy answers one question: given what has been measured so far, at
which temperature should the next expensive Monte Carlo experiment run?

These are the non-agent baselines the AI scientist is benchmarked against.
The LLM-agent strategy lives in the backend (it needs an LLM); it consumes the
same AcquisitionState.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from ..surrogate import ResponseSurrogate


@dataclass
class AcquisitionState:
    """Everything a strategy may condition on."""

    t_min: float
    t_max: float
    measured_temperatures: list[float] = field(default_factory=list)
    measured_values: list[float] = field(default_factory=list)  # susceptibility
    measured_errors: list[float] = field(default_factory=list)
    remaining_budget: int = 0

    def surrogate(self, seed: int = 0) -> ResponseSurrogate | None:
        if len(self.measured_temperatures) < ResponseSurrogate.MIN_POINTS:
            return None
        return ResponseSurrogate(
            self.measured_temperatures,
            self.measured_values,
            self.measured_errors,
            seed=seed,
        )


class Strategy(Protocol):
    name: str

    def propose(self, state: AcquisitionState) -> float: ...


def _largest_gap_midpoint(state: AcquisitionState) -> float:
    """Midpoint of the largest unmeasured gap, treating range ends as anchors."""
    pts = sorted(set(state.measured_temperatures) | {state.t_min, state.t_max})
    if len(pts) == 1:
        return 0.5 * (state.t_min + state.t_max)
    gaps = [(pts[i + 1] - pts[i], i) for i in range(len(pts) - 1)]
    width, i = max(gaps)
    if width <= 0:
        return 0.5 * (state.t_min + state.t_max)
    return 0.5 * (pts[i] + pts[i + 1])


class RandomStrategy:
    name = "random"

    def __init__(self, seed: int = 0):
        self._rng = np.random.default_rng(seed)

    def propose(self, state: AcquisitionState) -> float:
        return float(self._rng.uniform(state.t_min, state.t_max))


class GridStrategy:
    """Uniform-coverage baseline: repeatedly bisect the largest unmeasured gap."""

    name = "grid"

    def __init__(self, seed: int = 0):
        pass

    def propose(self, state: AcquisitionState) -> float:
        if not state.measured_temperatures:
            return state.t_min
        if len(state.measured_temperatures) == 1:
            return state.t_max
        return _largest_gap_midpoint(state)


class UncertaintyStrategy:
    """Measure where the bootstrap surrogate ensemble disagrees the most."""

    name = "uncertainty"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def propose(self, state: AcquisitionState) -> float:
        surrogate = state.surrogate(seed=self.seed)
        if surrogate is None:
            # Bootstrap phase: cover the range until a surrogate can be fit.
            return GridStrategy().propose(state)
        return surrogate.suggest_highest_uncertainty(
            state.t_min, state.t_max, exclude=state.measured_temperatures
        )


def make_strategy(name: str, seed: int = 0) -> Strategy:
    strategies = {
        "random": RandomStrategy,
        "grid": GridStrategy,
        "uncertainty": UncertaintyStrategy,
    }
    if name not in strategies:
        raise ValueError(f"unknown strategy {name!r}; expected one of {sorted(strategies)}")
    return strategies[name](seed=seed)
