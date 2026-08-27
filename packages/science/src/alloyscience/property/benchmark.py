"""Property-search benchmark (Milestone 8): with a finite query budget, does the
strategy recommend the stiffest truly-stable intermetallic?

Metric: regret = B_true(best stable) - B_true(recommended), plus whether the
recommendation is truly stable. Ground truth is exact (hidden CE + hidden B).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from functools import lru_cache

import numpy as np

from ..alloy.ground_truth import compute_ground_truth_from_energy_fn
from ..benchmark.alloy_harness import AlloyAcquisitionState, predicted_hull_from_state, propose_structure
from ..fcc import HiddenFccCE
from ..phase.mc import phase_system
from ..thermodynamics import lower_convex_hull
from .bulk_modulus import HiddenBulkModulusModel, PropertyOracle
from .ranking import rank_candidates

PROPERTY_STRATEGIES = ("random", "coverage", "uncertainty", "property")
DEFAULT_MAX_SIZE = 5


@lru_cache(maxsize=2)
def property_pool(max_size: int = DEFAULT_MAX_SIZE):
    """Structure pool on the MC-safe (4.5 A) cluster space, so fitted ECIs can
    drive canonical MC verification directly."""
    system = phase_system()
    return system, tuple(system.enumerate_pool(max_size=max_size))


@dataclass(frozen=True)
class PropertyGroundTruth:
    labels: list[str]
    x: list[float]
    e_form: list[float]
    bulk_modulus: list[float]
    stable_labels: list[str]
    best_label: str
    best_bulk_modulus: float
    ecis: list[float]
    b_model: dict

    def to_dict(self) -> dict:
        return asdict(self)


def compute_property_ground_truth(seed: int, max_size: int = DEFAULT_MAX_SIZE) -> PropertyGroundTruth:
    system, pool = property_pool(max_size)
    hidden = HiddenFccCE.random(system.n_parameters, seed=seed)
    b_model = HiddenBulkModulusModel.random(seed)
    truth = compute_ground_truth_from_energy_fn(list(pool), hidden.energy_per_site)
    bulk = [b_model.bulk_modulus(x, e) for x, e in zip(truth.x, truth.e_form)]
    stable = set(truth.stable_labels)
    intermetallics = [
        (b, lab) for lab, x, b in zip(truth.labels, truth.x, bulk)
        if lab in stable and x not in (0.0, 1.0)
    ]
    best_b, best_label = max(intermetallics) if intermetallics else max(zip(bulk, truth.labels))
    return PropertyGroundTruth(
        labels=truth.labels, x=truth.x, e_form=truth.e_form, bulk_modulus=bulk,
        stable_labels=truth.stable_labels, best_label=best_label,
        best_bulk_modulus=best_b, ecis=list(hidden.ecis), b_model=b_model.to_dict(),
    )


def fit_property_surrogate(state: AlloyAcquisitionState, bulk_by_index: dict[int, float], seed: int = 0):
    """Bootstrap linear model for B over cluster vectors (same design rows as the CE)."""
    from ..alloy.cluster_expansion import ClusterExpansionSurrogate

    idx = sorted(bulk_by_index)
    if len(idx) < ClusterExpansionSurrogate.MIN_POINTS:
        return None
    features = np.stack([state.pool[i].feature_vector() for i in idx])
    values = np.array([bulk_by_index[i] for i in idx])
    return ClusterExpansionSurrogate(features, values, seed=seed)


def predicted_candidates(state: AlloyAcquisitionState, bulk_by_index: dict[int, float], seed: int = 0,
                         verification_by_x: dict | None = None):
    """Full candidate table from current measurements + surrogates."""
    e_form, stable, hull_x, hull_e, e_form_std = predicted_hull_from_state(state, seed=seed)
    pool = state.pool
    hull = lower_convex_hull([s.x for s in pool], [e_form[s.label] for s in pool])
    b_surrogate = fit_property_surrogate(state, bulk_by_index, seed=seed)
    features = np.stack([s.feature_vector() for s in pool])
    if b_surrogate is not None:
        b_mean, b_std = b_surrogate.predict(features)
    else:
        b_mean, b_std = np.full(len(pool), np.nan), np.full(len(pool), np.inf)
    bulk, bulk_std = [], []
    for i, s in enumerate(pool):
        if i in bulk_by_index:
            bulk.append(float(bulk_by_index[i])); bulk_std.append(0.0)
        else:
            bulk.append(float(b_mean[i])); bulk_std.append(float(b_std[i]))
    surrogate = state.surrogate(seed=seed)
    loocv = surrogate.loocv_rmse() if surrogate is not None else float("nan")
    stable_tol = loocv if np.isfinite(loocv) else 1e-6
    return rank_candidates(
        labels=[s.label for s in pool], x=[s.x for s in pool],
        e_form=[e_form[s.label] for s in pool], e_form_std=[e_form_std[s.label] for s in pool],
        e_above_hull=list(hull.e_above_hull), bulk_modulus=bulk, bulk_modulus_std=bulk_std,
        measured=[i in state.measured_energies for i in range(len(pool))],
        stable_tol=stable_tol, verification_by_x=verification_by_x,
    ), stable_tol


def propose_property_query(state: AlloyAcquisitionState, bulk_by_index: dict[int, float],
                           strategy: str, rng: np.random.Generator) -> int:
    """Next structure index. 'property' = exploit: highest predicted score among
    unmeasured near-hull candidates, broken ties by uncertainty."""
    if strategy in ("random", "coverage", "uncertainty"):
        return propose_structure(state, strategy, rng)
    if strategy == "property":
        candidates, _ = predicted_candidates(state, bulk_by_index, seed=int(rng.integers(0, 2**31)))
        index_by_label = {s.label: i for i, s in enumerate(state.pool)}
        unmeasured = [c for c in candidates if not c.measured and c.x not in (0.0, 1.0)]
        if not unmeasured:
            return propose_structure(state, "coverage", rng)
        # Prefer stable-predicted high-B; fall back to high B with hull uncertainty.
        stable = [c for c in unmeasured if c.stable_0k]
        pick = max(stable or unmeasured, key=lambda c: c.bulk_modulus + c.e_form_std * 50.0)
        return index_by_label[pick.label]
    raise ValueError(f"unknown property strategy {strategy!r}; expected one of {PROPERTY_STRATEGIES}")


@dataclass(frozen=True)
class PropertyBenchmarkResult:
    problem: str
    strategy: str
    seed: int
    budget: int
    recommended_label: str | None
    recommended_true_b: float | None
    recommended_truly_stable: bool
    best_label: str
    best_bulk_modulus: float
    regret_gpa: float
    queried_labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def run_property_benchmark(strategy: str, budget: int, seed: int, max_size: int = DEFAULT_MAX_SIZE) -> PropertyBenchmarkResult:
    truth = compute_property_ground_truth(seed, max_size)
    system, pool = property_pool(max_size)
    pool = list(pool)
    hidden = HiddenFccCE.from_dict({"ecis": truth.ecis, "noise_sigma": 0.0})
    b_model = HiddenBulkModulusModel.from_dict(truth.b_model)
    idx_a = next(i for i, s in enumerate(pool) if s.x == 0.0)
    idx_b = next(i for i, s in enumerate(pool) if s.x == 1.0)
    oracle = PropertyOracle(hidden, b_model, hidden.energy_per_site(pool[idx_a]),
                            hidden.energy_per_site(pool[idx_b]), seed=seed)
    rng = np.random.default_rng(seed)
    state = AlloyAcquisitionState(pool=pool)
    bulk_by_index: dict[int, float] = {}
    q = 0
    for i in (idx_a, idx_b):
        e, b = oracle.evaluate(pool[i], query_seed=q); q += 1
        state.measured_energies[i] = e; bulk_by_index[i] = b
    while q < budget and state.unmeasured_indices():
        state.remaining_budget = budget - q
        i = propose_property_query(state, bulk_by_index, strategy, rng)
        e, b = oracle.evaluate(pool[i], query_seed=q); q += 1
        state.measured_energies[i] = e; bulk_by_index[i] = b

    candidates, _ = predicted_candidates(state, bulk_by_index, seed=seed)
    # Recommend the best MEASURED stable intermetallic (never an unverified prediction).
    rec = next((c for c in candidates if c.measured and c.stable_0k and c.x not in (0.0, 1.0)), None)
    true_b = dict(zip(truth.labels, truth.bulk_modulus))
    true_stable = set(truth.stable_labels)
    rec_b = true_b[rec.label] if rec else None
    return PropertyBenchmarkResult(
        problem="property", strategy=strategy, seed=seed, budget=budget,
        recommended_label=rec.label if rec else None,
        recommended_true_b=rec_b,
        recommended_truly_stable=bool(rec and rec.label in true_stable),
        best_label=truth.best_label, best_bulk_modulus=truth.best_bulk_modulus,
        regret_gpa=float(truth.best_bulk_modulus - rec_b) if rec_b is not None else float(truth.best_bulk_modulus),
        queried_labels=[pool[i].label for i in sorted(state.measured_energies)],
    )
