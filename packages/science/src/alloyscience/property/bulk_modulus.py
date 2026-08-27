"""Bulk modulus as a hidden property (Milestone 8).

Synthetic V3 problem: alongside the hidden cluster expansion for energies, a
hidden property model gives each ordering a bulk modulus. It is physically
flavoured — a Vegard-like baseline between B(Ni) ~ 180 GPa and B(Al) ~ 76 GPa
plus a stiffening bonus proportional to ordering strength (real intermetallics
are stiffer than their solid solutions) — so "stable AND stiff" is a genuine,
non-trivial trade-off the agent must resolve with few queries.

The oracle returns (energy, bulk modulus) per query, mirroring what the EMT
engine provides for real.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..errors import SimulationFailure

B_NI_GPA = 180.0
B_AL_GPA = 76.0


@dataclass(frozen=True)
class HiddenBulkModulusModel:
    b_a: float = B_NI_GPA
    b_b: float = B_AL_GPA
    ordering_gain: float = 100.0  # GPa per eV/atom of (negative) formation energy
    noise_sigma: float = 2.0

    @classmethod
    def random(cls, seed: int) -> "HiddenBulkModulusModel":
        rng = np.random.default_rng(seed + 7919)
        return cls(
            b_a=float(rng.uniform(165.0, 195.0)),
            b_b=float(rng.uniform(65.0, 85.0)),
            ordering_gain=float(rng.uniform(60.0, 140.0)),
            noise_sigma=2.0,
        )

    def bulk_modulus(self, x: float, e_form: float) -> float:
        baseline = (1.0 - x) * self.b_a + x * self.b_b
        return float(baseline + self.ordering_gain * max(0.0, -e_form))

    def to_dict(self) -> dict:
        return {
            "b_a": self.b_a,
            "b_b": self.b_b,
            "ordering_gain": self.ordering_gain,
            "noise_sigma": self.noise_sigma,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HiddenBulkModulusModel":
        return cls(**{k: float(d[k]) for k in ("b_a", "b_b", "ordering_gain", "noise_sigma") if k in d})


class PropertyOracle:
    """(energy per atom, bulk modulus) with deterministic noise and failure injection."""

    def __init__(self, energy_model, b_model: HiddenBulkModulusModel, e_pure_a: float,
                 e_pure_b: float, failure_rate: float = 0.0, seed: int = 0):
        self.energy_model = energy_model  # exposes energy_per_site(structure), noise_sigma
        self.b_model = b_model
        self.e_pure_a = e_pure_a
        self.e_pure_b = e_pure_b
        self.failure_rate = failure_rate
        self.seed = seed

    def evaluate(self, structure, query_seed: int = 0, is_retry: bool = False) -> tuple[float, float]:
        rng = np.random.default_rng((self.seed * 1_000_003 + query_seed) % (2**32))
        if self.failure_rate > 0 and not is_retry and rng.random() < self.failure_rate:
            raise SimulationFailure(
                category="SCF_NOT_CONVERGED",
                message="simulated electronic self-consistency failure (injected)",
                metadata={"structure": structure.label, "hint": "tighten mixing and retry"},
            )
        energy = self.energy_model.energy_per_site(structure) + float(
            rng.normal(0.0, self.energy_model.noise_sigma)
        )
        e_form_true = self.energy_model.energy_per_site(structure) - (
            (1.0 - structure.x) * self.e_pure_a + structure.x * self.e_pure_b
        )
        bulk = self.b_model.bulk_modulus(structure.x, e_form_true) + float(
            rng.normal(0.0, self.b_model.noise_sigma)
        )
        return float(energy), float(bulk)
