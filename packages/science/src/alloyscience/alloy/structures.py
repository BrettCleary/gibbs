"""Periodic binary-alloy configurations on a 2D square lattice (Milestone 3).

A structure is a periodic tile of pseudo-spins sigma in {-1 (A), +1 (B)} that
tiles the infinite lattice. Its energetics under ANY point/pair Hamiltonian are
fully determined by three correlation features (point, nearest-neighbour bond,
next-nearest-neighbour bond), so enumeration deduplicates on those features:
structures with identical correlations are energetically indistinguishable.

This is the V1 stand-in for icet's structure enumeration (Milestone 4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

import numpy as np

# Default tile shapes, capped at 9 sites so exhaustive enumeration stays cheap.
DEFAULT_SHAPES: tuple[tuple[int, int], ...] = (
    (1, 1),
    (1, 2),
    (2, 2),
    (1, 3),
    (2, 3),
    (1, 4),
    (2, 4),
    (3, 3),
)


def structure_features(occ: np.ndarray) -> tuple[float, float, float]:
    """(point, NN-bond, NNN-bond) correlations of a periodic tile.

    f_point = <sigma>
    f_nn    = <sigma_i sigma_j> averaged over nearest-neighbour bonds
    f_nnn   = <sigma_i sigma_j> averaged over next-nearest-neighbour bonds
    """
    occ = np.asarray(occ, dtype=float)
    f_point = float(occ.mean())
    f_nn = float(
        0.5 * ((occ * np.roll(occ, 1, axis=0)).mean() + (occ * np.roll(occ, 1, axis=1)).mean())
    )
    d1 = np.roll(np.roll(occ, 1, axis=0), 1, axis=1)
    d2 = np.roll(np.roll(occ, 1, axis=0), -1, axis=1)
    f_nnn = float(0.5 * ((occ * d1).mean() + (occ * d2).mean()))
    return (f_point, f_nn, f_nnn)


@dataclass(frozen=True)
class AlloyStructure:
    """One distinct periodic configuration A_(1-x)B_x."""

    label: str
    occupations: tuple[tuple[int, ...], ...]  # rows of -1/+1
    shape: tuple[int, int]
    x: float  # B fraction
    n_sites: int
    features: tuple[float, float, float] = field(default=(0.0, 0.0, 0.0))

    @property
    def array(self) -> np.ndarray:
        return np.array(self.occupations, dtype=int)

    def feature_vector(self) -> np.ndarray:
        """[1, f_point, f_nn, f_nnn] — the design row for the cluster expansion."""
        return np.array([1.0, *self.features])

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "occupations": [list(r) for r in self.occupations],
            "shape": list(self.shape),
            "x": self.x,
            "n_sites": self.n_sites,
            "features": list(self.features),
        }


def enumerate_structures(
    shapes: tuple[tuple[int, int], ...] = DEFAULT_SHAPES,
    x_min: float = 0.0,
    x_max: float = 1.0,
) -> list[AlloyStructure]:
    """All correlation-distinct periodic structures on the given tile shapes.

    Pure A (x=0) and pure B (x=1) are always included as reference endpoints,
    regardless of the composition window.
    """
    seen: dict[tuple, AlloyStructure] = {}
    for a, b in shapes:
        n = a * b
        for bits in product((-1, 1), repeat=n):
            occ = np.array(bits, dtype=int).reshape(a, b)
            x = float((occ == 1).mean())
            feats = structure_features(occ)
            key = (round(x, 6), *(round(f, 6) for f in feats))
            if key in seen:
                continue
            idx = len(seen)
            seen[key] = AlloyStructure(
                label=f"s{idx:03d}-{a}x{b}",
                occupations=tuple(tuple(int(v) for v in row) for row in occ),
                shape=(a, b),
                x=x,
                n_sites=n,
                features=feats,
            )
    structures = list(seen.values())
    kept = [
        s
        for s in structures
        if (x_min - 1e-9 <= s.x <= x_max + 1e-9) or s.x in (0.0, 1.0)
    ]
    return kept
