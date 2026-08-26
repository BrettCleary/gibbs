"""2D Ising model Monte Carlo simulator.

Ferromagnetic nearest-neighbour Ising model on an L x L square lattice with
periodic boundary conditions, J = 1, k_B = 1:

    H(sigma) = -J * sum_<ij> sigma_i sigma_j,   sigma_i in {-1, +1}

Sampling uses checkerboard Metropolis sweeps (vectorised with NumPy).
Statistical errors are estimated by blocking the measurement time series.

The exact infinite-lattice critical temperature (Onsager) is
    T_c = 2 / ln(1 + sqrt(2)) ~= 2.269185
Finite lattices show a shifted, rounded pseudo-critical peak; benchmark ground
truth should therefore be computed for the same L with a large budget rather
than compared against the Onsager value directly.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, asdict

import numpy as np

ONSAGER_TC = 2.0 / math.log(1.0 + math.sqrt(2.0))


@dataclass(frozen=True)
class IsingResult:
    """Observables from one Monte Carlo run at a single temperature."""

    temperature: float
    lattice_size: int
    n_sites: int
    n_equilibration_sweeps: int
    n_measurement_sweeps: int
    seed: int

    energy_per_site: float
    energy_per_site_err: float
    abs_magnetization: float
    abs_magnetization_err: float
    heat_capacity: float
    heat_capacity_err: float
    susceptibility: float
    susceptibility_err: float
    binder_cumulant: float

    wall_time_s: float
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class IsingSimulator:
    """Checkerboard Metropolis simulator for the 2D Ising model."""

    def __init__(self, lattice_size: int = 32):
        if lattice_size < 4 or lattice_size % 2 != 0:
            raise ValueError("lattice_size must be an even integer >= 4")
        self.lattice_size = lattice_size
        ix, iy = np.indices((lattice_size, lattice_size))
        self._parity_masks = [(ix + iy) % 2 == p for p in (0, 1)]

    # -- physics ------------------------------------------------------------

    def _neighbour_sum(self, spins: np.ndarray) -> np.ndarray:
        return (
            np.roll(spins, 1, axis=0)
            + np.roll(spins, -1, axis=0)
            + np.roll(spins, 1, axis=1)
            + np.roll(spins, -1, axis=1)
        )

    def _energy(self, spins: np.ndarray) -> float:
        # Each bond counted once: right and down neighbours.
        return float(
            -(spins * (np.roll(spins, 1, axis=0) + np.roll(spins, 1, axis=1))).sum()
        )

    def _sweep(self, spins: np.ndarray, beta: float, rng: np.random.Generator) -> None:
        for mask in self._parity_masks:
            nb = self._neighbour_sum(spins)
            d_e = 2.0 * spins * nb
            accept = (d_e <= 0.0) | (
                rng.random(spins.shape) < np.exp(-beta * np.clip(d_e, 0.0, None))
            )
            flip = mask & accept
            spins[flip] *= -1

    # -- public API ---------------------------------------------------------

    def run(
        self,
        temperature: float,
        n_equilibration_sweeps: int = 1000,
        n_measurement_sweeps: int = 4000,
        seed: int = 0,
    ) -> IsingResult:
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        t_start = time.monotonic()
        rng = np.random.default_rng(seed)
        n = self.lattice_size * self.lattice_size
        beta = 1.0 / temperature

        spins = rng.choice(np.array([-1, 1], dtype=np.int8), size=(self.lattice_size,) * 2)
        spins = spins.astype(np.int64)

        for _ in range(n_equilibration_sweeps):
            self._sweep(spins, beta, rng)

        energies = np.empty(n_measurement_sweeps)
        mags = np.empty(n_measurement_sweeps)
        for i in range(n_measurement_sweeps):
            self._sweep(spins, beta, rng)
            energies[i] = self._energy(spins)
            mags[i] = spins.mean()

        abs_m = np.abs(mags)
        e_site = energies / n

        energy_per_site, energy_err = _blocked_mean(e_site)
        abs_mag, abs_mag_err = _blocked_mean(abs_m)

        heat_capacity, heat_capacity_err = _blocked_derived(
            energies, lambda e: (e.var() / (n * temperature**2))
        )
        susceptibility, susceptibility_err = _blocked_derived(
            abs_m, lambda m: (n * m.var() / temperature)
        )

        m2 = float((mags**2).mean())
        m4 = float((mags**4).mean())
        binder = 1.0 - m4 / (3.0 * m2**2) if m2 > 0 else 0.0

        return IsingResult(
            temperature=float(temperature),
            lattice_size=self.lattice_size,
            n_sites=n,
            n_equilibration_sweeps=n_equilibration_sweeps,
            n_measurement_sweeps=n_measurement_sweeps,
            seed=seed,
            energy_per_site=float(energy_per_site),
            energy_per_site_err=float(energy_err),
            abs_magnetization=float(abs_mag),
            abs_magnetization_err=float(abs_mag_err),
            heat_capacity=float(heat_capacity),
            heat_capacity_err=float(heat_capacity_err),
            susceptibility=float(susceptibility),
            susceptibility_err=float(susceptibility_err),
            binder_cumulant=float(binder),
            wall_time_s=time.monotonic() - t_start,
            provenance={
                "engine": "alloyscience.ising.IsingSimulator",
                "algorithm": "checkerboard-metropolis",
                "numpy_version": np.__version__,
            },
        )


def _blocked_mean(series: np.ndarray, n_blocks: int = 20) -> tuple[float, float]:
    """Mean and blocking error of a (correlated) MC time series."""
    n_blocks = min(n_blocks, len(series))
    blocks = np.array_split(series, n_blocks)
    block_means = np.array([b.mean() for b in blocks])
    err = block_means.std(ddof=1) / math.sqrt(n_blocks) if n_blocks > 1 else 0.0
    return float(series.mean()), float(err)


def _blocked_derived(
    series: np.ndarray, statistic, n_blocks: int = 10
) -> tuple[float, float]:
    """A variance-based statistic and its error via jackknife-over-blocks."""
    value = float(statistic(series))
    n_blocks = min(n_blocks, len(series))
    if n_blocks < 3:
        return value, 0.0
    blocks = np.array_split(np.arange(len(series)), n_blocks)
    estimates = []
    for block in blocks:
        mask = np.ones(len(series), dtype=bool)
        mask[block] = False
        estimates.append(float(statistic(series[mask])))
    estimates = np.array(estimates)
    # Jackknife error over leave-one-block-out estimates.
    err = math.sqrt((n_blocks - 1) / n_blocks * ((estimates - estimates.mean()) ** 2).sum())
    return value, float(err)
