"""Canonical Monte Carlo sampling on a cluster expansion via mchammer (Milestone 4).

Given ECIs on an FccSystem's cluster space, sample the canonical ensemble
(fixed composition) at a temperature and report thermodynamic observables plus
the first-shell Warren-Cowley short-range-order parameter — the quantity that
distinguishes an ordered compound from a random solid solution. This is the
building block Milestone 5 sweeps over (x, T) to map the phase diagram.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from .system import FccSystem


@dataclass(frozen=True)
class CanonicalMCResult:
    temperature: float
    x: float
    n_sites: int
    n_trial_steps: int
    seed: int
    mean_energy_per_site: float
    energy_per_site_std: float
    sro_warren_cowley: float
    provenance: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _warren_cowley_first_shell(atoms, secondary: str, a: float) -> float:
    """alpha_1 = 1 - P(B neighbour of A)/x_B over the first FCC shell (r = a/sqrt(2))."""
    from ase.neighborlist import neighbor_list

    symbols = np.array(atoms.get_chemical_symbols())
    x_b = float((symbols == secondary).mean())
    if x_b in (0.0, 1.0):
        return 0.0
    cutoff = a / np.sqrt(2.0) * 1.1
    i_idx, j_idx = neighbor_list("ij", atoms, cutoff)
    a_sites = symbols[i_idx] != secondary
    if not a_sites.any():
        return 0.0
    p_b_given_a = float((symbols[j_idx[a_sites]] == secondary).mean())
    return float(1.0 - p_b_given_a / x_b)


def run_canonical_mc(
    system: FccSystem,
    ecis: list[float] | tuple[float, ...],
    x: float,
    temperature: float,
    supercell_repeat: int = 4,
    n_trial_steps: int = 20_000,
    seed: int = 0,
) -> CanonicalMCResult:
    import icet
    from icet import ClusterExpansion
    from mchammer.calculators import ClusterExpansionCalculator
    from mchammer.ensembles import CanonicalEnsemble

    ce = ClusterExpansion(system.cluster_space, np.asarray(ecis, dtype=float))
    supercell = system.primitive.repeat(supercell_repeat)
    n = len(supercell)
    n_b = int(round(x * n))
    rng = np.random.default_rng(seed)
    symbols = np.array([system.species[0]] * n, dtype=object)
    symbols[rng.choice(n, n_b, replace=False)] = system.species[1]
    supercell.set_chemical_symbols(list(symbols))

    calculator = ClusterExpansionCalculator(supercell, ce)
    ensemble = CanonicalEnsemble(
        structure=supercell,
        calculator=calculator,
        temperature=float(temperature),
        random_seed=seed,
        dc_filename=None,
    )
    ensemble.run(number_of_trial_steps=int(n_trial_steps))

    data = ensemble.data_container.data
    half = data["potential"].iloc[len(data) // 2 :] / n
    final_structure = ensemble.structure

    return CanonicalMCResult(
        temperature=float(temperature),
        x=float(n_b / n),
        n_sites=n,
        n_trial_steps=int(n_trial_steps),
        seed=seed,
        mean_energy_per_site=float(half.mean()),
        energy_per_site_std=float(half.std() if len(half) > 1 else 0.0),
        sro_warren_cowley=_warren_cowley_first_shell(
            final_structure, system.species[1], system.a
        ),
        provenance={
            "engine": "mchammer.CanonicalEnsemble",
            "icet_version": icet.__version__,
            "supercell_repeat": supercell_repeat,
        },
    )
