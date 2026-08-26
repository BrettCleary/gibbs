"""Exact ground truth and scoring for the hidden-Hamiltonian alloy problem.

Because the oracle is synthetic, the true hull is computable exactly — this is
what benchmark mode scores strategies against (plan section 21): missed stable
phases, falsely-predicted stable phases, and hull error.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np

from ..thermodynamics import lower_convex_hull
from .hamiltonian import HiddenPairHamiltonian
from .structures import AlloyStructure

STABLE_TOL = 1e-6


@dataclass(frozen=True)
class AlloyGroundTruth:
    labels: list[str]
    x: list[float]
    e_form: list[float]
    stable_labels: list[str]
    hull_x: list[float]
    hull_e: list[float]

    def to_dict(self) -> dict:
        return asdict(self)


def compute_ground_truth_from_energy_fn(pool, energy_per_site_fn) -> AlloyGroundTruth:
    """Exact ground truth for any structure pool given a noise-free energy function.

    Works for any pool items exposing `.label` and `.x` (2D tiles, FCC
    orderings, ...); formation energies are referenced to the pure endpoints.
    """
    energies = [energy_per_site_fn(s) for s in pool]
    e_a = next(e for s, e in zip(pool, energies) if s.x == 0.0)
    e_b = next(e for s, e in zip(pool, energies) if s.x == 1.0)
    x = [s.x for s in pool]
    e_form = [e - (1.0 - s.x) * e_a - s.x * e_b for s, e in zip(pool, energies)]
    hull = lower_convex_hull(x, e_form)
    stable = [s.label for s, on in zip(pool, hull.on_hull) if on]
    return AlloyGroundTruth(
        labels=[s.label for s in pool],
        x=x,
        e_form=e_form,
        stable_labels=stable,
        hull_x=hull.hull_x,
        hull_e=hull.hull_e,
    )


def compute_alloy_ground_truth(
    hamiltonian: HiddenPairHamiltonian, pool: list[AlloyStructure]
) -> AlloyGroundTruth:
    return compute_ground_truth_from_energy_fn(pool, hamiltonian.energy_per_site)


@dataclass(frozen=True)
class PredictionScore:
    missed_stable: list[str]
    false_stable: list[str]
    n_true_stable: int
    hull_rmse: float
    stable_energy_mae: float

    def to_dict(self) -> dict:
        return asdict(self)


def score_predictions(
    truth: AlloyGroundTruth,
    predicted_stable_labels: list[str],
    predicted_hull_x: list[float],
    predicted_hull_e: list[float],
    predicted_e_form_by_label: dict[str, float] | None = None,
    n_grid: int = 101,
) -> PredictionScore:
    true_set = set(truth.stable_labels)
    pred_set = set(predicted_stable_labels)
    grid = np.linspace(0.0, 1.0, n_grid)
    true_curve = np.interp(grid, truth.hull_x, truth.hull_e)
    pred_curve = np.interp(grid, predicted_hull_x, predicted_hull_e)
    hull_rmse = float(np.sqrt(np.mean((true_curve - pred_curve) ** 2)))

    stable_energy_mae = float("nan")
    if predicted_e_form_by_label:
        true_e = dict(zip(truth.labels, truth.e_form))
        errs = [
            abs(predicted_e_form_by_label[lab] - true_e[lab])
            for lab in true_set
            if lab in predicted_e_form_by_label
        ]
        if errs:
            stable_energy_mae = float(np.mean(errs))

    return PredictionScore(
        missed_stable=sorted(true_set - pred_set),
        false_stable=sorted(pred_set - true_set),
        n_true_stable=len(true_set),
        hull_rmse=hull_rmse,
        stable_energy_mae=stable_energy_mae,
    )
