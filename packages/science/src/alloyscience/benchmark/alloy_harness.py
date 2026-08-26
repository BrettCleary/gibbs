"""Acquisition strategies and benchmark harness for the alloy problem.

Same contract as the Ising harness: a strategy answers "which structure gets
the next expensive oracle query?", and the harness scores the final predicted
hull against exact ground truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

import numpy as np

from ..alloy.cluster_expansion import ClusterExpansionSurrogate
from ..alloy.ground_truth import (
    AlloyGroundTruth,
    PredictionScore,
    compute_alloy_ground_truth,
    score_predictions,
)
from ..alloy.hamiltonian import HiddenPairHamiltonian, StructureOracle
from ..alloy.structures import AlloyStructure, enumerate_structures
from ..thermodynamics import lower_convex_hull

ALLOY_STRATEGIES = ("random", "coverage", "uncertainty")


@dataclass
class AlloyAcquisitionState:
    pool: list[AlloyStructure]
    measured_energies: dict[int, float] = field(default_factory=dict)  # pool idx -> e/site
    remaining_budget: int = 0

    def unmeasured_indices(self) -> list[int]:
        return [i for i in range(len(self.pool)) if i not in self.measured_energies]

    def endpoint_energies(self) -> tuple[float, float] | None:
        try:
            idx_a = next(i for i, s in enumerate(self.pool) if s.x == 0.0)
            idx_b = next(i for i, s in enumerate(self.pool) if s.x == 1.0)
        except StopIteration:
            return None
        if idx_a not in self.measured_energies or idx_b not in self.measured_energies:
            return None
        return self.measured_energies[idx_a], self.measured_energies[idx_b]

    def surrogate(self, seed: int = 0) -> ClusterExpansionSurrogate | None:
        """CE fit over measured structures.

        Once both endpoints are measured the fit targets EXCESS energies
        (raw minus the composition-weighted endpoint reference). Pair and
        higher coefficients are invariant under this linear-in-x shift, but
        conditioning improves enormously when raw energies are large (real
        DFT totals are O(10^3) eV/atom while formation energies are O(0.1)) —
        without it, bootstrap members that drop a composition extrapolate
        absurdly. The returned surrogate carries `referenced=True` and then
        predicts formation-energy-like excess values directly.
        """
        if len(self.measured_energies) < ClusterExpansionSurrogate.MIN_POINTS:
            return None
        idx = sorted(self.measured_energies)
        features = np.stack([self.pool[i].feature_vector() for i in idx])
        energies = np.array([self.measured_energies[i] for i in idx])
        endpoints = self.endpoint_energies()
        referenced = endpoints is not None
        if referenced:
            e_a, e_b = endpoints
            xs = np.array([self.pool[i].x for i in idx])
            energies = energies - ((1.0 - xs) * e_a + xs * e_b)
        surrogate = ClusterExpansionSurrogate(features, energies, seed=seed)
        surrogate.referenced = referenced
        return surrogate


def propose_structure(state: AlloyAcquisitionState, strategy: str, rng: np.random.Generator) -> int:
    """Pool index of the next structure to query under a baseline strategy."""
    unmeasured = state.unmeasured_indices()
    if not unmeasured:
        raise ValueError("no unmeasured structures remain")
    if strategy == "random":
        return int(rng.choice(unmeasured))
    if strategy == "coverage":
        measured_x = [state.pool[i].x for i in state.measured_energies]
        if not measured_x:
            return int(rng.choice(unmeasured))
        gaps = [min(abs(state.pool[i].x - mx) for mx in measured_x) for i in unmeasured]
        best = max(gaps)
        candidates = [i for i, g in zip(unmeasured, gaps) if g >= best - 1e-12]
        return int(rng.choice(candidates))
    if strategy == "uncertainty":
        surrogate = state.surrogate(seed=int(rng.integers(0, 2**31)))
        if surrogate is None:
            return propose_structure(state, "coverage", rng)
        features = np.stack([state.pool[i].feature_vector() for i in unmeasured])
        _, std = surrogate.predict(features)
        return int(unmeasured[int(np.argmax(std))])
    raise ValueError(f"unknown alloy strategy {strategy!r}; expected one of {ALLOY_STRATEGIES}")


def predicted_hull_from_state(
    state: AlloyAcquisitionState, seed: int = 0, stable_tol: float | None = None
) -> tuple[dict[str, float], list[str], list[float], list[float], dict[str, float]]:
    """Predicted formation energies + stable set from measurements and surrogate.

    Measured structures use their measured energies; unmeasured use surrogate
    predictions. A structure counts as predicted-stable when its energy above
    the hull is within `stable_tol`; by default that tolerance is the model's
    own LOOCV RMSE (agent-knowable, adapts to measurement noise), so degenerate
    hull structures are not spuriously "lost" to noise. Returns
    (e_form_by_label, stable_labels, hull_x, hull_e, e_form_std_by_label).
    """
    pool = state.pool
    idx_a = next(i for i, s in enumerate(pool) if s.x == 0.0)
    idx_b = next(i for i, s in enumerate(pool) if s.x == 1.0)
    if idx_a not in state.measured_energies or idx_b not in state.measured_energies:
        raise ValueError("endpoint references must be measured before predicting a hull")
    e_a = state.measured_energies[idx_a]
    e_b = state.measured_energies[idx_b]

    surrogate = state.surrogate(seed=seed)
    features = np.stack([s.feature_vector() for s in pool])
    if surrogate is not None:
        mean, std = surrogate.predict(features)
        referenced = getattr(surrogate, "referenced", False)
    else:
        mean = np.zeros(len(pool))
        std = np.full(len(pool), np.inf)
        referenced = False

    e_form: dict[str, float] = {}
    e_form_std: dict[str, float] = {}
    for i, s in enumerate(pool):
        reference = (1.0 - s.x) * e_a + s.x * e_b
        if i in state.measured_energies:
            e_form[s.label] = float(state.measured_energies[i] - reference)
        elif referenced:
            e_form[s.label] = float(mean[i])  # excess energy IS the formation energy
        else:
            e_form[s.label] = float(mean[i] - reference)
        e_form_std[s.label] = 0.0 if i in state.measured_energies else float(std[i])

    hull = lower_convex_hull([s.x for s in pool], [e_form[s.label] for s in pool])
    if stable_tol is None:
        loocv = surrogate.loocv_rmse() if surrogate is not None else float("nan")
        stable_tol = loocv if np.isfinite(loocv) else 1e-6
    stable = [
        s.label for s, e_above in zip(pool, hull.e_above_hull) if e_above <= stable_tol + 1e-12
    ]
    return e_form, stable, hull.hull_x, hull.hull_e, e_form_std


@dataclass(frozen=True)
class AlloyBenchmarkResult:
    problem: str
    strategy: str
    seed: int
    budget: int
    pool_size: int
    hidden_params: dict
    queried_labels: list[str]
    score: PredictionScore
    loocv_rmse: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["score"] = self.score.to_dict()
        # Flatten headline metrics for easy tabulation.
        d["hull_rmse"] = self.score.hull_rmse
        d["n_missed_stable"] = len(self.score.missed_stable)
        d["n_false_stable"] = len(self.score.false_stable)
        return d


def run_acquisition_benchmark(
    problem: str,
    strategy: str,
    budget: int,
    seed: int,
    pool,
    oracle: StructureOracle,
    truth,
    hidden_params: dict,
) -> AlloyBenchmarkResult:
    """Generic hull-discovery benchmark over any structure pool + oracle.

    Pool items must expose `.label`, `.x`, and `.feature_vector()`.
    """
    if budget < ClusterExpansionSurrogate.MIN_POINTS:
        raise ValueError(f"budget must be >= {ClusterExpansionSurrogate.MIN_POINTS}")

    rng = np.random.default_rng(seed)
    state = AlloyAcquisitionState(pool=list(pool))

    # References first: pure A and pure B (consumes 2 budget units, like real DFT).
    idx_a = next(i for i, s in enumerate(state.pool) if s.x == 0.0)
    idx_b = next(i for i, s in enumerate(state.pool) if s.x == 1.0)
    query_counter = 0
    for i in (idx_a, idx_b):
        state.measured_energies[i] = oracle.evaluate(state.pool[i], query_seed=query_counter)
        query_counter += 1

    while query_counter < budget and state.unmeasured_indices():
        state.remaining_budget = budget - query_counter
        i = propose_structure(state, strategy, rng)
        state.measured_energies[i] = oracle.evaluate(state.pool[i], query_seed=query_counter)
        query_counter += 1

    e_form, stable, hull_x, hull_e, _ = predicted_hull_from_state(state, seed=seed)
    score = score_predictions(truth, stable, hull_x, hull_e, e_form)
    surrogate = state.surrogate(seed=seed)
    return AlloyBenchmarkResult(
        problem=problem,
        strategy=strategy,
        seed=seed,
        budget=budget,
        pool_size=len(state.pool),
        hidden_params=hidden_params,
        queried_labels=[state.pool[i].label for i in sorted(state.measured_energies)],
        score=score,
        loocv_rmse=surrogate.loocv_rmse() if surrogate else float("nan"),
    )


def run_alloy_benchmark(
    strategy: str,
    budget: int,
    seed: int,
    hamiltonian: HiddenPairHamiltonian | None = None,
    pool: list[AlloyStructure] | None = None,
) -> AlloyBenchmarkResult:
    """One strategy run against a hidden 2D pair Hamiltonian (random per seed)."""
    if pool is None:
        pool = enumerate_structures()
    if hamiltonian is None:
        hamiltonian = HiddenPairHamiltonian.random(seed=seed)
    truth = compute_alloy_ground_truth(hamiltonian, pool)
    oracle = StructureOracle(hamiltonian, failure_rate=0.0, seed=seed)
    return run_acquisition_benchmark(
        "alloy", strategy, budget, seed, pool, oracle, truth,
        hidden_params={"j1": hamiltonian.j1, "j2": hamiltonian.j2},
    )


def run_fcc_benchmark(
    strategy: str,
    budget: int,
    seed: int,
    max_size: int | None = None,
) -> AlloyBenchmarkResult:
    """One strategy run against a hidden icet cluster expansion on FCC (V2)."""
    from ..alloy.ground_truth import compute_ground_truth_from_energy_fn
    from ..fcc import HiddenFccCE
    from ..fcc.system import DEFAULT_MAX_SIZE, cached_system_and_pool

    system, pool = cached_system_and_pool(max_size=max_size or DEFAULT_MAX_SIZE)
    hidden = HiddenFccCE.random(system.n_parameters, seed=seed)
    truth = compute_ground_truth_from_energy_fn(list(pool), hidden.energy_per_site)
    oracle = StructureOracle(hidden, failure_rate=0.0, seed=seed)
    return run_acquisition_benchmark(
        "fcc", strategy, budget, seed, list(pool), oracle, truth,
        hidden_params={"ecis": list(hidden.ecis)},
    )
