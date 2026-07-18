from __future__ import annotations

import numpy as np
from groovy.executor.control import normalize_curve_points, values_from_curve_points


def test_values_from_curve_points_linear_fallback() -> None:
    values = values_from_curve_points(None, 5, start_value=0.0, end_value=1.0)
    assert values.shape == (5,)
    np.testing.assert_allclose(values[0], 0.0)
    np.testing.assert_allclose(values[-1], 1.0)


def test_values_from_curve_points_piecewise() -> None:
    points = [{"t": 0, "v": 0}, {"t": 0.5, "v": 1}, {"t": 1, "v": 0}]
    values = values_from_curve_points(points, 5)
    np.testing.assert_allclose(values[0], 0.0, atol=1e-9)
    np.testing.assert_allclose(values[2], 1.0, atol=1e-9)
    np.testing.assert_allclose(values[-1], 0.0, atol=1e-9)


def test_normalize_curve_points_adds_endpoints() -> None:
    pairs = normalize_curve_points([{"t": 0.25, "v": 0.5}, {"t": 0.75, "v": 0.8}])
    assert pairs[0][0] == 0.0
    assert pairs[-1][0] == 1.0
