"""The hidden binary-alloy Hamiltonian — the 'expensive oracle' of Milestone 3.

    E/site = 2*J1*<sigma sigma>_NN + 2*J2*<sigma sigma>_NNN

(the factor 2 is bonds-per-site on the square lattice; a point term would
cancel in formation energies, so it is omitted). J1 > 0 favours unlike
neighbours -> ordered compounds with negative formation energy; J2 tilts which
orderings win. The agent never sees J1/J2 — it can only query structure
energies through StructureOracle, which adds simulated measurement noise and
charges one budget unit per call.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

from ..errors import SimulationFailure
from .structures import AlloyStructure


@dataclass(frozen=True)
class HiddenPairHamiltonian:
    j1: float
    j2: float
    noise_sigma: float = 0.0

    @classmethod
    def random(cls, seed: int, noise_sigma: float | None = None) -> "HiddenPairHamiltonian":
        rng = np.random.default_rng(seed)
        j1 = float(rng.uniform(0.4, 1.2))
        j2 = float(rng.uniform(-0.4, 0.6))
        if noise_sigma is None:
            noise_sigma = 0.01 * 4.0 * j1
        return cls(j1=j1, j2=j2, noise_sigma=float(noise_sigma))

    def energy_per_site(self, structure: AlloyStructure) -> float:
        """Exact (noise-free) energy per site."""
        _, f_nn, f_nnn = structure.features
        return float(2.0 * self.j1 * f_nn + 2.0 * self.j2 * f_nnn)

    def formation_energy(self, structure: AlloyStructure) -> float:
        """Exact formation energy per site vs pure A / pure B (both have e = 2*J1+2*J2)."""
        e_pure = 2.0 * self.j1 + 2.0 * self.j2
        return self.energy_per_site(structure) - e_pure

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HiddenPairHamiltonian":
        return cls(j1=float(d["j1"]), j2=float(d["j2"]), noise_sigma=float(d.get("noise_sigma", 0.0)))


class StructureOracle:
    """Noisy, per-query-costed access to the hidden Hamiltonian.

    Noise is deterministic per (structure, seed) so retried queries reproduce.
    Optional failure injection mimics DFT SCF non-convergence for the
    failure-recovery demo; retries (is_retry=True) never re-inject.
    """

    def __init__(
        self,
        hamiltonian: HiddenPairHamiltonian,
        failure_rate: float = 0.0,
        seed: int = 0,
    ):
        self.hamiltonian = hamiltonian
        self.failure_rate = failure_rate
        self.seed = seed

    def evaluate(
        self, structure: AlloyStructure, query_seed: int = 0, is_retry: bool = False
    ) -> float:
        rng = np.random.default_rng((self.seed * 1_000_003 + query_seed) % (2**32))
        if self.failure_rate > 0 and not is_retry and rng.random() < self.failure_rate:
            raise SimulationFailure(
                category="SCF_NOT_CONVERGED",
                message="simulated electronic self-consistency failure "
                "(injected for recovery testing)",
                metadata={
                    "structure": structure.label,
                    "hint": "tighten mixing / increase iterations and retry",
                },
            )
        noise = float(rng.normal(0.0, self.hamiltonian.noise_sigma))
        return self.hamiltonian.energy_per_site(structure) + noise
