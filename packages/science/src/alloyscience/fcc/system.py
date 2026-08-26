"""FCC binary-alloy system built on ASE + icet (Milestone 4).

icet provides the crystallographically real machinery — primitive cell,
cluster space, symmetry-distinct structure enumeration, cluster vectors —
and the cluster vector is the design row for CE fitting, exactly as the
correlation features were for the 2D toy problem (V1). Enumerated structures
that share a cluster vector are energetically indistinguishable for any CE on
this cluster space, so the pool is deduplicated on cluster vectors.

icet imports are deliberately lazy: the first import compiles/loads slowly and
most of the codebase does not need it.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from functools import lru_cache

import numpy as np

DEFAULT_A = 3.52  # Ni lattice constant, Angstrom
DEFAULT_CUTOFFS = (5.5,)  # pairs out to ~1.5 a
DEFAULT_SPECIES = ("Ni", "Al")
DEFAULT_MAX_SIZE = 5  # atoms per enumerated cell


@dataclass(frozen=True)
class FccStructure:
    """One symmetry/correlation-distinct FCC ordering, self-contained (no ASE needed)."""

    label: str
    x: float  # fraction of species[1] (Al)
    n_sites: int
    chemical_formula: str
    cluster_vector: tuple[float, ...]
    cell: tuple[tuple[float, float, float], ...]
    positions: tuple[tuple[float, float, float], ...]
    atomic_numbers: tuple[int, ...]

    def feature_vector(self) -> np.ndarray:
        """The CE design row (icet cluster vector; element 0 is the zerolet = 1)."""
        return np.array(self.cluster_vector)

    def to_dict(self) -> dict:
        return asdict(self)


class FccSystem:
    def __init__(
        self,
        a: float = DEFAULT_A,
        cutoffs: tuple[float, ...] = DEFAULT_CUTOFFS,
        species: tuple[str, str] = DEFAULT_SPECIES,
    ):
        from ase.build import bulk
        from icet import ClusterSpace

        self.a = a
        self.cutoffs = tuple(cutoffs)
        self.species = tuple(species)
        self.primitive = bulk(species[0], "fcc", a=a)
        self.cluster_space = ClusterSpace(
            self.primitive, list(self.cutoffs), chemical_symbols=list(self.species)
        )

    @property
    def n_parameters(self) -> int:
        return len(self.cluster_space)

    def enumerate_pool(
        self,
        max_size: int = DEFAULT_MAX_SIZE,
        x_min: float = 0.0,
        x_max: float = 1.0,
    ) -> list[FccStructure]:
        """Cluster-vector-distinct orderings on cells of up to `max_size` atoms.

        The pure endpoints are always kept as formation-energy references.
        """
        from icet.tools import enumerate_structures

        seen: dict[tuple, FccStructure] = {}
        secondary = self.species[1]
        for atoms in enumerate_structures(
            self.primitive, range(1, max_size + 1), list(self.species)
        ):
            symbols = atoms.get_chemical_symbols()
            x = symbols.count(secondary) / len(symbols)
            cv = self.cluster_space.get_cluster_vector(atoms)
            key = tuple(round(float(v), 8) for v in cv)
            if key in seen:
                continue
            idx = len(seen)
            seen[key] = FccStructure(
                label=f"f{idx:03d}-n{len(atoms)}",
                x=float(x),
                n_sites=len(atoms),
                chemical_formula=atoms.get_chemical_formula(),
                cluster_vector=key,
                cell=tuple(tuple(float(v) for v in row) for row in atoms.get_cell()),
                positions=tuple(
                    tuple(float(v) for v in pos) for pos in atoms.get_positions()
                ),
                atomic_numbers=tuple(int(z) for z in atoms.get_atomic_numbers()),
            )
        return [
            s
            for s in seen.values()
            if (x_min - 1e-9 <= s.x <= x_max + 1e-9) or s.x in (0.0, 1.0)
        ]


@lru_cache(maxsize=4)
def cached_system_and_pool(
    a: float = DEFAULT_A,
    cutoffs: tuple[float, ...] = DEFAULT_CUTOFFS,
    species: tuple[str, str] = DEFAULT_SPECIES,
    max_size: int = DEFAULT_MAX_SIZE,
) -> tuple[FccSystem, tuple[FccStructure, ...]]:
    system = FccSystem(a=a, cutoffs=cutoffs, species=species)
    return system, tuple(system.enumerate_pool(max_size=max_size))
