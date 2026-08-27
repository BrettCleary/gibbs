"""Classical-potential energy calculator: ASE's effective-medium theory (EMT).

The 'cheap real calculator' rung between the synthetic oracle and DFT. For
each structure it optimises the isotropic cell volume (mixed compositions
relax away from the pure-Ni lattice) and reports the equilibrium energy plus
the curvature-derived bulk modulus — the seed observable for Milestone 8.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from ..errors import SimulationFailure
from ..fcc.system import FccStructure
from .base import EnergyResult, structure_to_atoms, vegard_scale

EV_PER_A3_TO_GPA = 160.21766

# Elements ASE's EMT is parameterised for (bulk metals only).
EMT_ELEMENTS = frozenset({"Al", "Cu", "Ag", "Au", "Ni", "Pd", "Pt"})


class EmtFccCalculator:
    name = "emt"

    def __init__(self, scale_bounds: tuple[float, float] = (0.90, 1.35), a_parent: float = 3.52):
        self.scale_bounds = scale_bounds
        self.a_parent = a_parent

    def _energy_at_scale(self, structure: FccStructure, scale: float) -> float:
        from ase.calculators.emt import EMT

        atoms = structure_to_atoms(structure, scale=scale)
        atoms.calc = EMT()
        return float(atoms.get_potential_energy())

    def compute(self, structure: FccStructure, workdir: Path | None = None) -> EnergyResult:
        from ase.data import chemical_symbols

        unsupported = sorted({chemical_symbols[z] for z in structure.atomic_numbers} - EMT_ELEMENTS)
        if unsupported:
            raise SimulationFailure(
                category="ENGINE_UNAVAILABLE",
                message=f"EMT has no parameters for {unsupported}; supported: {sorted(EMT_ELEMENTS)}",
                metadata={"engine": "emt", "unsupported_elements": unsupported},
            )
        result = minimize_scalar(
            lambda s: self._energy_at_scale(structure, s),
            bounds=self.scale_bounds,
            method="bounded",
            options={"xatol": 1e-4},
        )
        s_opt = float(result.x)
        e_opt = float(result.fun)
        n = structure.n_sites

        # Curvature -> bulk modulus: B = V d2E/dV2 = (d2E/ds2) / (9 V0 s) at the
        # minimum (V = V0 s^3, dE/ds = 0 there).
        ds = 0.004
        e_plus = self._energy_at_scale(structure, s_opt + ds)
        e_minus = self._energy_at_scale(structure, s_opt - ds)
        d2e_ds2 = (e_plus - 2.0 * e_opt + e_minus) / ds**2
        v0 = float(abs(np.linalg.det(np.array(structure.cell))))
        bulk_modulus_gpa = float(d2e_ds2 / (9.0 * v0 * s_opt) * EV_PER_A3_TO_GPA)

        return EnergyResult(
            energy_per_atom=e_opt / n,
            lattice_scale=s_opt,
            details={
                "engine": "ase.calculators.emt.EMT",
                "volume_optimised": True,
                "optimal_lattice_constant": self.a_parent * s_opt,
                "vegard_lattice_scale": vegard_scale(structure),
                "bulk_modulus_gpa": bulk_modulus_gpa,
            },
        )
