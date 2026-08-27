"""Curated element catalog for FCC-parent-lattice alloy campaigns.

Common alloying metals with lattice data from ASE's reference states. Each
entry records the element's ambient crystal structure so the UI and the report
can flag pairs that only make sense as a *hypothetical* FCC alloy.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

# Metals that are reasonable on an FCC parent lattice (natively FCC or common
# FCC-alloy formers) and have simple reference lattice data (Mn, In, Sn are
# excluded: complex/tetragonal reference structures). Symbol order = Z order.
CATALOG_SYMBOLS = (
    "Mg", "Al", "Sc", "Ti", "V", "Cr", "Fe", "Co", "Ni", "Cu", "Zn",
    "Y", "Zr", "Nb", "Mo", "Ru", "Rh", "Pd", "Ag", "Cd",
    "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Pb",
)


@dataclass(frozen=True)
class ElementInfo:
    symbol: str
    name: str
    atomic_number: int
    structure: str  # ambient reference structure: fcc | bcc | hcp | ...
    fcc_native: bool
    a_fcc: float  # FCC lattice constant used for the parent lattice (A)
    emt: bool  # ASE EMT has parameters

    def to_dict(self) -> dict:
        return asdict(self)


def element_info(symbol: str) -> ElementInfo:
    from ase.data import atomic_names, atomic_numbers, reference_states

    from .base import fcc_lattice_constant
    from .emt import EMT_ELEMENTS

    if symbol not in atomic_numbers:
        raise ValueError(f"unknown element symbol {symbol!r}")
    z = atomic_numbers[symbol]
    ref = reference_states[z] or {}
    structure = str(ref.get("symmetry") or "unknown")
    return ElementInfo(
        symbol=symbol,
        name=atomic_names[z],
        atomic_number=z,
        structure=structure,
        fcc_native=structure == "fcc",
        a_fcc=fcc_lattice_constant(symbol),
        emt=symbol in EMT_ELEMENTS,
    )


def element_catalog() -> list[ElementInfo]:
    """Catalog entries; elements without usable reference lattice data are skipped."""
    out = []
    for s in CATALOG_SYMBOLS:
        try:
            out.append(element_info(s))
        except ValueError:
            continue
    return out


def is_catalog_element(symbol: str) -> bool:
    return symbol in CATALOG_SYMBOLS
