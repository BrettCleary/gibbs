"""EnergyCalculator: the abstraction boundary of plan section 2.2.

    structure -> ASE Atoms -> Calculator -> energy

Everything above this interface (agent, cluster expansion, hull, campaigns)
is calculator-agnostic: the synthetic oracle, the EMT classical potential,
and Quantum ESPRESSO plug in interchangeably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..fcc.system import FccStructure

# Reference FCC lattice constants (Angstrom) for Vegard interpolation.
LATTICE_CONSTANTS = {"Ni": 3.52, "Al": 4.05}


@dataclass(frozen=True)
class EnergyResult:
    energy_per_atom: float  # eV, at the calculator's chosen geometry
    lattice_scale: float  # applied isotropic scale relative to the input cell
    details: dict = field(default_factory=dict)
    log_path: str | None = None  # engine log artifact, if any


class EnergyCalculator(Protocol):
    name: str

    def compute(self, structure: FccStructure, workdir: Path | None = None) -> EnergyResult: ...


def structure_to_atoms(structure: FccStructure, scale: float = 1.0):
    """Self-contained FccStructure -> periodic ASE Atoms (optionally rescaled)."""
    import numpy as np
    from ase import Atoms

    cell = np.array(structure.cell) * scale
    positions = np.array(structure.positions) * scale
    return Atoms(
        numbers=list(structure.atomic_numbers),
        positions=positions,
        cell=cell,
        pbc=True,
    )


def vegard_scale(structure: FccStructure, a_reference: float = LATTICE_CONSTANTS["Ni"]) -> float:
    """Vegard's-law lattice scale for composition x (pool cells are built at a_Ni)."""
    a_x = (1.0 - structure.x) * LATTICE_CONSTANTS["Ni"] + structure.x * LATTICE_CONSTANTS["Al"]
    return a_x / a_reference
