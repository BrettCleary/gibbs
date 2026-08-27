"""One (x, T) phase-diagram experiment: canonical MC on a cluster expansion.

Observables per run (the expensive experiment of Milestone 5):
- heat capacity per atom in units of k_B (from energy fluctuations, with a
  jackknife error over blocks) — its peak locates the order/disorder transition;
- the first-shell Warren-Cowley short-range-order parameter averaged over the
  sampling window (alpha < 0: unlike-neighbour order; ~0: random solution).

The phase problem uses a 4.5 Angstrom pair cutoff so a 4x4x4 primitive
supercell (64 atoms) has no calculator self-interaction.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, asdict
from functools import lru_cache

import numpy as np

from ..ising.simulator import _blocked_derived, _blocked_mean
from ..fcc.system import PHASE_RELATIVE_CUTOFFS, FccSystem, cutoffs_for

KB_EV = 8.617333262e-5  # Boltzmann constant, eV/K
PHASE_CUTOFFS = (4.5,)  # for a = 3.52; other lattice constants scale via cutoffs_for
DEFAULT_SUPERCELL_REPEAT = 4
DEFAULT_TRIAL_STEPS = 20_000


@lru_cache(maxsize=8)
def phase_system(a: float = 3.52, species: tuple[str, str] = ("Ni", "Al")) -> FccSystem:
    """Cluster space used by the phase problem (short cutoffs so a 4x4x4
    primitive supercell has no calculator self-interaction), for any element pair."""
    return FccSystem(a=a, cutoffs=cutoffs_for(a, PHASE_RELATIVE_CUTOFFS), species=species)


@dataclass(frozen=True)
class PhasePoint:
    x: float
    temperature: float
    n_sites: int
    n_trial_steps: int
    seed: int
    heat_capacity: float  # k_B per atom
    heat_capacity_err: float
    sro: float  # Warren-Cowley alpha_1
    sro_err: float
    mean_energy_per_site: float
    wall_time_s: float
    provenance: dict

    def to_dict(self) -> dict:
        return asdict(self)


def run_phase_point(
    system: FccSystem,
    ecis: list[float] | tuple[float, ...],
    x: float,
    temperature: float,
    supercell_repeat: int = DEFAULT_SUPERCELL_REPEAT,
    n_trial_steps: int = DEFAULT_TRIAL_STEPS,
    seed: int = 0,
) -> PhasePoint:
    import icet
    from icet import ClusterExpansion
    from mchammer.calculators import ClusterExpansionCalculator
    from mchammer.ensembles import CanonicalEnsemble
    from mchammer.observers import BinaryShortRangeOrderObserver

    if not 0.0 < x < 1.0:
        raise ValueError("composition x must be strictly between 0 and 1 for canonical MC")
    if temperature <= 0:
        raise ValueError("temperature must be positive (Kelvin)")

    t_start = time.monotonic()
    ce = ClusterExpansion(system.cluster_space, np.asarray(ecis, dtype=float))
    supercell = system.primitive.repeat(supercell_repeat)
    n = len(supercell)
    n_b = int(round(x * n))
    rng = np.random.default_rng(seed)
    symbols = np.array([system.species[0]] * n, dtype=object)
    symbols[rng.choice(n, n_b, replace=False)] = system.species[1]
    supercell.set_chemical_symbols(list(symbols))

    ensemble = CanonicalEnsemble(
        structure=supercell,
        calculator=ClusterExpansionCalculator(supercell, ce),
        temperature=float(temperature),
        random_seed=seed,
        dc_filename=None,
    )
    observer = BinaryShortRangeOrderObserver(
        system.cluster_space, supercell, interval=n * 2, radius=system.a / np.sqrt(2) * 1.05
    )
    ensemble.attach_observer(observer)
    ensemble.run(number_of_trial_steps=int(n_trial_steps))

    data = ensemble.data_container.data
    half = data.iloc[len(data) // 2 :]
    e_site = (half["potential"] / n).to_numpy()
    sro_series = half["sro_Al_1"].dropna().to_numpy()

    # C/k_B per atom = Var(E_site) * n / (k_B T)^2
    scale = n / (KB_EV * float(temperature)) ** 2
    heat_capacity, heat_capacity_err = _blocked_derived(
        e_site, lambda e: float(e.var() * scale), n_blocks=8
    )
    sro, sro_err = _blocked_mean(sro_series, n_blocks=8)

    return PhasePoint(
        x=float(n_b / n),
        temperature=float(temperature),
        n_sites=n,
        n_trial_steps=int(n_trial_steps),
        seed=seed,
        heat_capacity=float(heat_capacity),
        heat_capacity_err=float(heat_capacity_err),
        sro=float(sro),
        sro_err=float(sro_err),
        mean_energy_per_site=float(e_site.mean()),
        wall_time_s=time.monotonic() - t_start,
        provenance={
            "engine": "mchammer.CanonicalEnsemble",
            "icet_version": icet.__version__,
            "cluster_space_cutoffs": list(system.cutoffs),
            "supercell_repeat": supercell_repeat,
            "heat_capacity_units": "k_B per atom",
        },
    )


__all__ = ["PhasePoint", "phase_system", "run_phase_point", "KB_EV"]
