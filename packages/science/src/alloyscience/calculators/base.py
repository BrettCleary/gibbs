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

# Reference FCC lattice constants (Angstrom) for the original Ni-Al problem;
# any other element is looked up via `fcc_lattice_constant` (ASE reference data).
LATTICE_CONSTANTS = {"Ni": 3.52, "Al": 4.05}


def fcc_lattice_constant(symbol: str) -> float:
    """FCC lattice constant (A) for an element from ASE's reference states.

    FCC elements use their tabulated `a` directly; BCC/HCP elements get the
    lattice constant of an FCC cell with the same atomic volume, so any metal
    can be placed on the FCC parent lattice used by the alloy problems.
    """
    import math

    from ase.data import atomic_numbers, reference_states

    if symbol in LATTICE_CONSTANTS:
        return LATTICE_CONSTANTS[symbol]
    if symbol not in atomic_numbers:
        raise ValueError(f"unknown element symbol {symbol!r}")
    ref = reference_states[atomic_numbers[symbol]] or {}
    sym, a = ref.get("symmetry"), ref.get("a")
    if a is None:
        raise ValueError(f"no reference lattice data for {symbol!r}; cannot build an FCC parent lattice")
    if sym == "fcc":
        return float(a)
    if sym == "bcc":
        volume = a**3 / 2.0
    elif sym == "hcp":
        c = a * float(ref.get("c/a") or 1.633)
        volume = (math.sqrt(3.0) / 2.0) * a * a * c / 2.0
    elif sym == "diamond":
        volume = a**3 / 8.0
    elif sym == "sc":
        volume = a**3
    else:
        raise ValueError(f"{symbol!r} reference structure {sym!r} is not supported for an FCC parent lattice")
    return float((4.0 * volume) ** (1.0 / 3.0))


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


def parent_lattice_constant(structure: FccStructure) -> float:
    """The FCC lattice constant the structure's cell was built at, from its
    geometry: an n-site FCC cell has volume n * a^3 / 4."""
    import numpy as np

    volume = float(abs(np.linalg.det(np.array(structure.cell))))
    return float((4.0 * volume / structure.n_sites) ** (1.0 / 3.0))


def vegard_scale(
    structure: FccStructure,
    a_reference: float | None = None,
    a_by_number: dict[int, float] | None = None,
) -> float:
    """Vegard's-law lattice scale for the structure's composition.

    The target lattice constant is the composition-weighted average of the two
    elements' FCC lattice constants (looked up by atomic number); the scale is
    relative to the parent lattice the cell was built at (element A's), which
    defaults to the value derived from the cell geometry.
    """
    from ase.data import chemical_symbols

    numbers = sorted(set(structure.atomic_numbers))
    if a_by_number is None:
        a_by_number = {z: fcc_lattice_constant(chemical_symbols[z]) for z in numbers}
    n = structure.n_sites
    if len(numbers) == 1:
        a_a = a_b = a_by_number[numbers[0]]
    else:
        # x is the fraction of species B: B is the species whose count matches x.
        z_b = min(numbers, key=lambda z: abs(structure.atomic_numbers.count(z) / n - structure.x))
        z_a = next(z for z in numbers if z != z_b)
        a_a, a_b = a_by_number[z_a], a_by_number[z_b]
    if a_reference is None:
        a_reference = parent_lattice_constant(structure)
    a_x = (1.0 - structure.x) * a_a + structure.x * a_b
    return a_x / a_reference
