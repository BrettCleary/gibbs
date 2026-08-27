import os
from pathlib import Path

import pytest

from alloyscience.calculators import (
    EmtFccCalculator,
    EspressoConfig,
    EspressoFccCalculator,
    espresso_available,
    structure_to_atoms,
    vegard_scale,
)
from alloyscience.errors import SimulationFailure
from alloyscience.fcc.system import cached_system_and_pool


@pytest.fixture(scope="module")
def pool():
    _, pool = cached_system_and_pool(max_size=4)
    return list(pool)


def test_structure_to_atoms_roundtrip(pool):
    s = next(s for s in pool if s.n_sites > 1)
    atoms = structure_to_atoms(s, scale=1.1)
    assert len(atoms) == s.n_sites
    assert atoms.pbc.all()
    import numpy as np

    assert np.allclose(np.array(atoms.get_cell()), np.array(s.cell) * 1.1)


def test_vegard_scale_endpoints(pool):
    pure_ni = next(s for s in pool if s.x == 0.0)
    pure_al = next(s for s in pool if s.x == 1.0)
    assert vegard_scale(pure_ni) == pytest.approx(1.0)
    assert vegard_scale(pure_al) == pytest.approx(4.05 / 3.52)


def test_emt_calculator_physical_sanity(pool):
    pure_ni = next(s for s in pool if s.x == 0.0)
    pure_al = next(s for s in pool if s.x == 1.0)
    emt = EmtFccCalculator()
    r_ni = emt.compute(pure_ni)
    r_al = emt.compute(pure_al)
    # Equilibrium lattice constants near experiment (EMT is parameterised for these).
    assert r_ni.details["optimal_lattice_constant"] == pytest.approx(3.52, abs=0.1)
    assert r_al.details["optimal_lattice_constant"] == pytest.approx(4.05, abs=0.1)
    # Bulk moduli in a physical range (GPa): Ni ~ 180, Al ~ 76 experimentally.
    assert 100 < r_ni.details["bulk_modulus_gpa"] < 260
    assert 20 < r_al.details["bulk_modulus_gpa"] < 120
    assert r_ni.details["bulk_modulus_gpa"] > r_al.details["bulk_modulus_gpa"]


def test_emt_is_deterministic(pool):
    s = next(s for s in pool if 0 < s.x < 1)
    emt = EmtFccCalculator()
    assert emt.compute(s).energy_per_atom == emt.compute(s).energy_per_atom


def test_espresso_available_reports_missing():
    ok, reason = espresso_available(EspressoConfig(pw_command="/nonexistent/pw.x"))
    assert not ok and "pw.x" in reason
    ok, reason = espresso_available(
        EspressoConfig(pw_command="/bin/ls", pseudo_dir="/nonexistent")
    )
    assert not ok and "pseudo" in reason.lower()


def test_espresso_unavailable_raises_categorised_failure(pool):
    calc = EspressoFccCalculator(EspressoConfig(pw_command="/nonexistent/pw.x"))
    with pytest.raises(SimulationFailure) as exc:
        calc.compute(pool[0], workdir=Path("/tmp/never-used"))
    assert exc.value.category == "ENGINE_UNAVAILABLE"


@pytest.mark.skipif(
    not os.environ.get("ALLOYLAB_PW_COMMAND"),
    reason="set ALLOYLAB_PW_COMMAND (and ALLOYLAB_PSEUDO_DIR) to run real DFT tests",
)
def test_espresso_real_scf_on_pure_ni(pool, tmp_path):
    cfg = EspressoConfig(
        pw_command=os.environ["ALLOYLAB_PW_COMMAND"],
        pseudo_dir=os.environ.get("ALLOYLAB_PSEUDO_DIR", "infra/pseudopotentials"),
        kspacing=0.5,
    )
    ok, reason = espresso_available(cfg)
    if not ok:
        pytest.skip(reason)
    pure_ni = next(s for s in pool if s.x == 0.0)
    result = EspressoFccCalculator(cfg).compute(pure_ni, workdir=tmp_path / "ni")
    assert result.energy_per_atom < -1000  # PAW total energies are large and negative
    assert result.details["scf_iterations"] is not None
    assert Path(result.log_path).is_file()
    assert "JOB DONE" in Path(result.log_path).read_text(errors="replace")


def test_espresso_volume_scan_eos_math(pool, monkeypatch):
    """E(V) scan -> parabola minimum and bulk modulus, with a mocked SCF."""
    from alloyscience.calculators.base import EnergyResult
    from alloyscience.calculators.espresso import EspressoFccCalculator

    pure_ni = next(s for s in pool if s.x == 0.0)
    v0 = abs(__import__("numpy").linalg.det(__import__("numpy").array(pure_ni.cell)))
    k = 5.0  # eV per unit scale^2 curvature -> known B
    s_min = 1.02

    def fake_single_point(self, structure, scale, workdir):
        return EnergyResult(energy_per_atom=k * (scale - s_min) ** 2 - 10.0, lattice_scale=scale,
                            details={"scf_iterations": 3})

    monkeypatch.setattr(EspressoFccCalculator, "_single_point", fake_single_point)
    cfg = EspressoConfig(pw_command="/bin/ls", pseudo_dir="/nonexistent", n_volumes=5)
    monkeypatch.setattr("alloyscience.calculators.espresso.espresso_available", lambda c: (True, "ok"))
    r = EspressoFccCalculator(cfg).compute(pure_ni, workdir=Path("/tmp/eos-test"))
    assert r.lattice_scale == pytest.approx(s_min, abs=1e-6)
    assert r.energy_per_atom == pytest.approx(-10.0, abs=1e-6)
    expected_b = (2 * k) / (9 * v0 * s_min) * 160.21766
    assert r.details["bulk_modulus_gpa"] == pytest.approx(expected_b, rel=1e-6)


@pytest.mark.skipif(
    not os.environ.get("ALLOYLAB_PW_COMMAND"),
    reason="set ALLOYLAB_PW_COMMAND to run the real E(V) scan",
)
def test_espresso_real_bulk_modulus_of_ni(pool, tmp_path):
    cfg = EspressoConfig(
        pw_command=os.environ["ALLOYLAB_PW_COMMAND"],
        pseudo_dir=os.environ.get("ALLOYLAB_PSEUDO_DIR", "infra/pseudopotentials"),
        kspacing=0.35, n_volumes=5,
    )
    ok, reason = espresso_available(cfg)
    if not ok:
        pytest.skip(reason)
    pure_ni = next(s for s in pool if s.x == 0.0)
    r = EspressoFccCalculator(cfg).compute(pure_ni, workdir=tmp_path / "eos")
    # PBE bulk modulus of fcc Ni ~ 190-200 GPa; demo settings within a broad window.
    assert 120 < r.details["bulk_modulus_gpa"] < 280
    assert 0.95 < r.lattice_scale < 1.06
    assert len(r.details["energies_ev"]) == 5


def test_lattice_constants_from_reference_data():
    from alloyscience.calculators import fcc_lattice_constant, parent_lattice_constant

    assert fcc_lattice_constant("Cu") == pytest.approx(3.61, abs=0.02)
    assert fcc_lattice_constant("Au") == pytest.approx(4.08, abs=0.02)
    # BCC Fe -> equal-atomic-volume FCC cell: a = 2.87 * 2^(1/3)
    assert fcc_lattice_constant("Fe") == pytest.approx(2.87 * 2 ** (1 / 3), rel=1e-3)
    with pytest.raises(ValueError):
        fcc_lattice_constant("Xx")


def test_vegard_and_parent_for_any_pair():
    from alloyscience.calculators import parent_lattice_constant
    from alloyscience.fcc.system import cached_system_and_pool, cutoffs_for

    a_cu = 3.61
    system, pool = cached_system_and_pool(a=a_cu, cutoffs=cutoffs_for(a_cu), species=("Cu", "Au"), max_size=3)
    assert system.n_parameters == cached_system_and_pool(max_size=3)[0].n_parameters  # same pair shells as Ni-Al
    pure_cu = next(s for s in pool if s.x == 0.0); pure_au = next(s for s in pool if s.x == 1.0)
    assert parent_lattice_constant(pure_au) == pytest.approx(a_cu, rel=1e-6)
    assert vegard_scale(pure_cu) == pytest.approx(1.0)
    assert vegard_scale(pure_au) == pytest.approx(4.08 / a_cu, rel=1e-3)
    mixed = next(s for s in pool if 0 < s.x < 1)
    expected = ((1 - mixed.x) * 3.61 + mixed.x * 4.08) / a_cu
    assert vegard_scale(mixed) == pytest.approx(expected, rel=1e-3)
    assert "Cu" in mixed.chemical_formula and "Au" in mixed.chemical_formula


def test_emt_rejects_unsupported_elements(pool):
    from alloyscience.fcc.system import FccStructure

    s = pool[0]
    fake = FccStructure(label="x", x=0.0, n_sites=s.n_sites, chemical_formula="Fe", cluster_vector=s.cluster_vector,
                        cell=s.cell, positions=s.positions, atomic_numbers=tuple(26 for _ in s.atomic_numbers))
    with pytest.raises(SimulationFailure) as exc:
        EmtFccCalculator().compute(fake)
    assert exc.value.category == "ENGINE_UNAVAILABLE"


def test_resolve_pseudopotentials(tmp_path):
    from alloyscience.calculators import resolve_pseudopotentials

    (tmp_path / "Cu.pbe-dn-kjpaw_psl.1.0.0.UPF").write_text("x")
    (tmp_path / "Cu.pz-old.UPF").write_text("x")
    found, missing = resolve_pseudopotentials(tmp_path, ["Cu", "Au"])
    assert found == {"Cu": "Cu.pbe-dn-kjpaw_psl.1.0.0.UPF"} and missing == ["Au"]
