import math

import numpy as np
import pytest

from alloyscience.ising import IsingSimulator, ONSAGER_TC


def test_onsager_constant():
    assert ONSAGER_TC == pytest.approx(2.269185, abs=1e-5)


def test_low_temperature_is_ordered():
    sim = IsingSimulator(lattice_size=16)
    r = sim.run(1.0, n_equilibration_sweeps=300, n_measurement_sweeps=500, seed=1)
    # Deep in the ferromagnetic phase: nearly full magnetisation, energy near -2 J/site.
    assert r.abs_magnetization > 0.95
    assert r.energy_per_site == pytest.approx(-2.0, abs=0.05)


def test_high_temperature_is_disordered():
    sim = IsingSimulator(lattice_size=16)
    r = sim.run(5.0, n_equilibration_sweeps=300, n_measurement_sweeps=500, seed=2)
    assert r.abs_magnetization < 0.3
    assert r.energy_per_site > -1.0


def test_susceptibility_peaks_near_critical_temperature():
    sim = IsingSimulator(lattice_size=16)
    temps = [1.2, 1.8, 2.3, 2.9, 3.5]
    chis = [
        sim.run(t, n_equilibration_sweeps=400, n_measurement_sweeps=1200, seed=3).susceptibility
        for t in temps
    ]
    assert temps[int(np.argmax(chis))] == pytest.approx(2.3)


def test_determinism_with_seed():
    sim = IsingSimulator(lattice_size=8)
    a = sim.run(2.2, n_equilibration_sweeps=50, n_measurement_sweeps=100, seed=7)
    b = sim.run(2.2, n_equilibration_sweeps=50, n_measurement_sweeps=100, seed=7)
    assert a.energy_per_site == b.energy_per_site
    assert a.susceptibility == b.susceptibility


def test_invalid_inputs():
    with pytest.raises(ValueError):
        IsingSimulator(lattice_size=5)
    with pytest.raises(ValueError):
        IsingSimulator(lattice_size=8).run(-1.0)


def test_error_bars_reported():
    sim = IsingSimulator(lattice_size=8)
    r = sim.run(2.3, n_equilibration_sweeps=100, n_measurement_sweeps=400, seed=4)
    assert r.energy_per_site_err > 0
    assert r.susceptibility_err > 0
    assert math.isfinite(r.heat_capacity_err)
