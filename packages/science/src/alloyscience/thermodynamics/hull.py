"""Formation energies and the lower convex hull for a binary system A_(1-x)B_x.

Groundwork for Milestone 3 (binary lattice model); unit-tested now so the
thermodynamics layer is trustworthy before it is wired into campaigns.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np


def formation_energy(
    energy_per_atom: float, x: float, energy_a: float, energy_b: float
) -> float:
    """Formation energy per atom relative to the pure endpoints.

    delta_E = E(A_(1-x)B_x) - (1-x) E(A) - x E(B)
    """
    if not 0.0 <= x <= 1.0:
        raise ValueError("composition x must be in [0, 1]")
    return float(energy_per_atom - (1.0 - x) * energy_a - x * energy_b)


@dataclass(frozen=True)
class HullResult:
    hull_x: list[float]
    hull_e: list[float]
    e_above_hull: list[float]
    on_hull: list[bool]

    def to_dict(self) -> dict:
        return asdict(self)


def lower_convex_hull(
    x: np.ndarray | list[float],
    e_form: np.ndarray | list[float],
    tol: float = 1e-9,
) -> HullResult:
    """Lower convex hull of formation energies vs composition.

    The endpoints (x=0 and x=1) are pinned at zero formation energy if not
    supplied. Returns hull vertices sorted by composition and, for every input
    point, its energy above the hull and whether it lies on the hull.
    """
    x_arr = np.asarray(x, dtype=float)
    e_arr = np.asarray(e_form, dtype=float)
    if x_arr.shape != e_arr.shape or x_arr.ndim != 1:
        raise ValueError("x and e_form must be 1-D arrays of equal length")
    if np.any((x_arr < 0) | (x_arr > 1)):
        raise ValueError("compositions must lie in [0, 1]")

    pts_x = x_arr.tolist()
    pts_e = e_arr.tolist()
    if not np.any(np.isclose(x_arr, 0.0)):
        pts_x.append(0.0)
        pts_e.append(0.0)
    if not np.any(np.isclose(x_arr, 1.0)):
        pts_x.append(1.0)
        pts_e.append(0.0)
    px = np.array(pts_x)
    pe = np.array(pts_e)

    # Never let positive-energy points anchor the hull ends: endpoints at 0.
    # Andrew's monotone chain, lower hull only.
    order = np.lexsort((pe, px))
    hull: list[tuple[float, float]] = []
    for i in order:
        p = (float(px[i]), float(pe[i]))
        while len(hull) >= 2:
            (x1, y1), (x2, y2) = hull[-2], hull[-1]
            cross = (x2 - x1) * (p[1] - y1) - (p[0] - x1) * (y2 - y1)
            if cross <= tol:
                hull.pop()
            else:
                break
        hull.append(p)
    # Keep only points with e <= 0 (hull of a binary cannot rise above endpoints).
    hull = [(hx, he) for hx, he in hull if he <= tol]
    hull_x = [h[0] for h in hull]
    hull_e = [h[1] for h in hull]

    hull_x_arr = np.array(hull_x)
    hull_e_arr = np.array(hull_e)
    e_above = []
    on_hull = []
    for xi, ei in zip(x_arr, e_arr):
        e_hull = float(np.interp(xi, hull_x_arr, hull_e_arr))
        dist = float(ei - e_hull)
        e_above.append(max(dist, 0.0))
        on_hull.append(abs(dist) <= 1e-6)
    return HullResult(hull_x=hull_x, hull_e=hull_e, e_above_hull=e_above, on_hull=on_hull)
