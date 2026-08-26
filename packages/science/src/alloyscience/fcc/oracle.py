"""Hidden ground-truth cluster expansion for the FCC problem (plan section 22, V2).

The 'expensive oracle' is a known-but-hidden icet-style cluster expansion:
energy per atom = ECI · cluster_vector. A positive nearest-neighbour pair ECI
favours unlike neighbours, producing ordered compounds (L1_2/L1_0-like) with
negative formation energies — the physics the agent must discover.

Satisfies the same duck-typed protocol as HiddenPairHamiltonian
(`energy_per_site`, `noise_sigma`), so alloyscience's StructureOracle,
ground-truth, and acquisition machinery work unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .system import FccStructure


@dataclass(frozen=True)
class HiddenFccCE:
    ecis: tuple[float, ...]
    noise_sigma: float = 0.0

    @classmethod
    def random(
        cls, n_parameters: int, seed: int, noise_sigma: float | None = None
    ) -> "HiddenFccCE":
        """Physically-flavoured random ECIs (eV/atom).

        Index 0 is the zerolet (constant), 1 the singlet; both cancel in
        formation energies. Index 2 is the nearest-neighbour pair — drawn
        positive so ordering is favoured; further orbits decay in magnitude.
        """
        rng = np.random.default_rng(seed)
        ecis = np.zeros(n_parameters)
        if n_parameters > 1:
            ecis[1] = rng.uniform(-0.02, 0.02)
        if n_parameters > 2:
            ecis[2] = rng.uniform(0.04, 0.12)
        for i in range(3, n_parameters):
            ecis[i] = rng.uniform(-0.03, 0.03) / (i - 1)
        if noise_sigma is None:
            noise_sigma = 0.05 * float(ecis[2]) if n_parameters > 2 else 0.003
        return cls(ecis=tuple(float(v) for v in ecis), noise_sigma=float(noise_sigma))

    def energy_per_site(self, structure: FccStructure) -> float:
        return float(np.dot(self.ecis, structure.feature_vector()))

    def to_dict(self) -> dict:
        return {"ecis": list(self.ecis), "noise_sigma": self.noise_sigma}

    @classmethod
    def from_dict(cls, d: dict) -> "HiddenFccCE":
        return cls(
            ecis=tuple(float(v) for v in d["ecis"]),
            noise_sigma=float(d.get("noise_sigma", 0.0)),
        )
