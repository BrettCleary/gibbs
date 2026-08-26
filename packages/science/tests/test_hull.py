import pytest

from alloyscience.thermodynamics import formation_energy, lower_convex_hull


def test_formation_energy_endpoints_zero():
    assert formation_energy(-4.0, 0.0, -4.0, -3.0) == pytest.approx(0.0)
    assert formation_energy(-3.0, 1.0, -4.0, -3.0) == pytest.approx(0.0)


def test_formation_energy_mixture():
    # E = -5, linear reference = 0.5*(-4) + 0.5*(-3) = -3.5 -> delta = -1.5
    assert formation_energy(-5.0, 0.5, -4.0, -3.0) == pytest.approx(-1.5)


def test_formation_energy_invalid_composition():
    with pytest.raises(ValueError):
        formation_energy(-1.0, 1.5, 0.0, 0.0)


def test_hull_single_stable_compound():
    x = [0.0, 0.25, 0.5, 0.75, 1.0]
    e = [0.0, -0.1, -0.4, -0.1, 0.0]
    hull = lower_convex_hull(x, e)
    assert hull.on_hull == [True, False, True, False, True]
    assert hull.e_above_hull[0] == pytest.approx(0.0)
    assert hull.e_above_hull[2] == pytest.approx(0.0)
    # x=0.25 sits above the tie line from (0,0) to (0.5,-0.4): hull energy -0.2
    assert hull.e_above_hull[1] == pytest.approx(0.1)


def test_hull_all_positive_energies():
    x = [0.3, 0.6]
    e = [0.2, 0.5]
    hull = lower_convex_hull(x, e)
    # Nothing mixes: hull is just the endpoints at zero.
    assert hull.hull_x == [0.0, 1.0]
    assert hull.e_above_hull == [pytest.approx(0.2), pytest.approx(0.5)]
    assert hull.on_hull == [False, False]


def test_hull_two_compounds():
    x = [0.0, 0.25, 0.5, 0.75, 1.0]
    e = [0.0, -0.3, -0.35, -0.05, 0.0]
    hull = lower_convex_hull(x, e)
    assert hull.on_hull[1] and hull.on_hull[2]
    assert not hull.on_hull[3]
