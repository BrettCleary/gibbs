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
