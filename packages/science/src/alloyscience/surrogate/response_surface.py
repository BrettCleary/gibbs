"""Bootstrap-ensemble surrogate for an observable-vs-temperature response curve.

This is the V0 analogue of the cluster-expansion surrogate: measurements are
expensive Monte Carlo runs at chosen temperatures; the surrogate predicts the
full response curve (e.g. susceptibility chi(T)) with uncertainty, and the peak
location provides a critical-temperature estimate with an uncertainty derived
from ensemble disagreement.

Method: each ensemble member resamples the measured points with replacement and
perturbs them by their reported measurement errors, then fits a Gaussian-kernel
(Nadaraya-Watson) smoother. Predictive mean/std across the ensemble provide the
acquisition signal for active learning.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np


@dataclass(frozen=True)
class SurrogatePrediction:
    temperatures: list[float]
    mean: list[float]
    std: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TcEstimate:
    mean: float
    std: float
    samples: list[float] = field(default_factory=list)
    # True when most ensemble members put the peak at a range edge: the real
    # peak likely lies outside the window, so `mean` is a bound, not a
    # location, and the small `std` must not be read as confidence.
    edge_pinned: bool = False

    def to_dict(self) -> dict:
        return {"mean": self.mean, "std": self.std, "edge_pinned": self.edge_pinned}


class ResponseSurrogate:
    """Ensemble of kernel smoothers over (temperature, observable) data."""

    MIN_POINTS = 3

    def __init__(
        self,
        temperatures: np.ndarray | list[float],
        values: np.ndarray | list[float],
        errors: np.ndarray | list[float] | None = None,
        n_ensemble: int = 40,
        bandwidth: float | None = None,
        seed: int = 0,
    ):
        self.t = np.asarray(temperatures, dtype=float)
        self.y = np.asarray(values, dtype=float)
        if len(self.t) < self.MIN_POINTS:
            raise ValueError(
                f"surrogate requires at least {self.MIN_POINTS} measured points, got {len(self.t)}"
            )
        if errors is None:
            errors = np.zeros_like(self.y)
        self.yerr = np.asarray(errors, dtype=float)
        order = np.argsort(self.t)
        self.t, self.y, self.yerr = self.t[order], self.y[order], self.yerr[order]

        if bandwidth is None:
            spacings = np.diff(np.unique(self.t))
            med = float(np.median(spacings)) if len(spacings) else 0.2
            span = float(self.t.max() - self.t.min()) or 1.0
            bandwidth = max(med, 0.05 * span)
        self.bandwidth = float(bandwidth)
        self.n_ensemble = n_ensemble
        self._rng = np.random.default_rng(seed)
        self._members = self._fit_ensemble()

    def _fit_ensemble(self) -> list[tuple[np.ndarray, np.ndarray]]:
        members = []
        n = len(self.t)
        for _ in range(self.n_ensemble):
            idx = self._rng.integers(0, n, size=n)
            t_b = self.t[idx]
            y_b = self.y[idx] + self._rng.normal(0.0, 1.0, size=n) * self.yerr[idx]
            members.append((t_b, y_b))
        return members

    def _kernel_predict(self, t_b: np.ndarray, y_b: np.ndarray, grid: np.ndarray) -> np.ndarray:
        # Nadaraya-Watson with Gaussian kernel.
        d = grid[:, None] - t_b[None, :]
        w = np.exp(-0.5 * (d / self.bandwidth) ** 2)
        w_sum = w.sum(axis=1)
        w_sum[w_sum == 0] = 1e-300
        return (w * y_b[None, :]).sum(axis=1) / w_sum

    def predict(self, grid: np.ndarray | list[float]) -> SurrogatePrediction:
        grid = np.asarray(grid, dtype=float)
        preds = np.stack([self._kernel_predict(t_b, y_b, grid) for t_b, y_b in self._members])
        return SurrogatePrediction(
            temperatures=grid.tolist(),
            mean=preds.mean(axis=0).tolist(),
            std=preds.std(axis=0).tolist(),
        )

    def estimate_peak(self, t_min: float, t_max: float, n_grid: int = 400) -> TcEstimate:
        """Peak location (e.g. pseudo-critical temperature) with ensemble spread."""
        grid = np.linspace(t_min, t_max, n_grid)
        peaks = []
        for t_b, y_b in self._members:
            pred = self._kernel_predict(t_b, y_b, grid)
            peaks.append(float(grid[int(np.argmax(pred))]))
        peaks_arr = np.array(peaks)
        margin = 0.02 * (t_max - t_min)
        at_edge = (peaks_arr <= t_min + margin) | (peaks_arr >= t_max - margin)
        return TcEstimate(
            mean=float(peaks_arr.mean()),
            std=float(peaks_arr.std()),
            samples=peaks,
            edge_pinned=bool(at_edge.mean() > 0.5),
        )

    def acquisition_uncertainty(
        self, t_min: float, t_max: float, n_grid: int = 200
    ) -> tuple[np.ndarray, np.ndarray]:
        """Grid and predictive std over it — the raw uncertainty-sampling signal."""
        grid = np.linspace(t_min, t_max, n_grid)
        pred = self.predict(grid)
        return grid, np.asarray(pred.std)

    def suggest_highest_uncertainty(
        self,
        t_min: float,
        t_max: float,
        exclude: list[float] | None = None,
        min_separation: float | None = None,
        n_grid: int = 200,
    ) -> float:
        """Temperature with maximal predictive uncertainty, avoiding measured points."""
        grid, std = self.acquisition_uncertainty(t_min, t_max, n_grid)
        exclude_arr = np.array(exclude if exclude is not None else self.t.tolist())
        if min_separation is None:
            min_separation = 0.02 * (t_max - t_min)
        if len(exclude_arr):
            dist = np.abs(grid[:, None] - exclude_arr[None, :]).min(axis=1)
            std = np.where(dist < min_separation, -np.inf, std)
        return float(grid[int(np.argmax(std))])

    def suggest_peak_refinement(
        self,
        t_min: float,
        t_max: float,
        exclude: list[float] | None = None,
        min_separation: float | None = None,
    ) -> float:
        """Best next measurement for locating the PEAK of the response.

        Raw max-std acquisition chases the range edges, where kernel smoothers
        extrapolate with huge variance but the peak rarely lives. Instead,
        sample from the ensemble's own peak-location distribution: candidate
        temperatures are the per-member peak positions, and the one farthest
        from any existing measurement is chosen — concentrating queries where
        the peak plausibly sits and the data is thinnest.
        """
        est = self.estimate_peak(t_min, t_max)
        exclude_arr = np.array(exclude if exclude is not None else self.t.tolist())
        if min_separation is None:
            min_separation = 0.02 * (t_max - t_min)
        candidates = np.array(est.samples if est.samples else [est.mean])
        if len(exclude_arr) == 0:
            return float(np.median(candidates))
        dist = np.abs(candidates[:, None] - exclude_arr[None, :]).min(axis=1)
        best = float(candidates[int(np.argmax(dist))])
        if dist.max() >= min_separation:
            return best
        # Peak region saturated with measurements: fall back to max-std.
        return self.suggest_highest_uncertainty(
            t_min, t_max, exclude=list(exclude_arr), min_separation=min_separation
        )
