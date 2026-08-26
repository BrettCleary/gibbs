import numpy as np
import pytest

from alloyscience.surrogate import ResponseSurrogate


def _peaked_data(n=9, peak=2.3, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.linspace(1.5, 3.5, n)
    y = np.exp(-((t - peak) ** 2) / 0.08) * 40 + 1.0
    y = y + rng.normal(0, noise, size=n)
    err = np.full(n, max(noise, 1e-6))
    return t, y, err


def test_requires_minimum_points():
    with pytest.raises(ValueError):
        ResponseSurrogate([2.0, 2.5], [1.0, 2.0])


def test_peak_recovery():
    t, y, err = _peaked_data(n=11)
    s = ResponseSurrogate(t, y, err, seed=1)
    est = s.estimate_peak(1.5, 3.5)
    assert est.mean == pytest.approx(2.3, abs=0.15)


def test_uncertainty_shrinks_with_more_data():
    t5, y5, e5 = _peaked_data(n=5, noise=1.0, seed=2)
    t15, y15, e15 = _peaked_data(n=15, noise=1.0, seed=2)
    s5 = ResponseSurrogate(t5, y5, e5, seed=3)
    s15 = ResponseSurrogate(t15, y15, e15, seed=3)
    assert s15.estimate_peak(1.5, 3.5).std <= s5.estimate_peak(1.5, 3.5).std + 0.05


def test_suggestion_avoids_measured_points():
    t, y, err = _peaked_data(n=6, noise=0.5, seed=4)
    s = ResponseSurrogate(t, y, err, seed=4)
    suggestion = s.suggest_highest_uncertainty(1.5, 3.5)
    assert 1.5 <= suggestion <= 3.5
    assert min(abs(suggestion - ti) for ti in t) > 0.02


def test_prediction_shapes():
    t, y, err = _peaked_data(n=7)
    s = ResponseSurrogate(t, y, err)
    grid = np.linspace(1.5, 3.5, 50)
    pred = s.predict(grid)
    assert len(pred.mean) == 50
    assert len(pred.std) == 50
    assert all(v >= 0 for v in pred.std)
