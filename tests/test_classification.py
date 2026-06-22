"""Tests for ABC-XYZ portfolio classification (capability M4).

ABC = importance by annual usage value (cumulative Pareto cut).
XYZ = predictability by demand coefficient of variation.
The 9-cell matrix assigns a default review policy + service-level target per SKU.
"""

import math

import pytest

from src.classification import SkuClassification, classify_portfolio


def _items():
    return [
        {"product_id": "A1", "unit_cost": 4.0, "demand": [50, 50, 50, 50]},   # high value, stable
        {"product_id": "A2", "unit_cost": 2.0, "demand": [60, 60, 60, 60]},   # high value, stable
        {"product_id": "B1", "unit_cost": 1.0, "demand": [20, 40, 20, 40]},   # mid value
        {"product_id": "C1", "unit_cost": 0.5, "demand": [0, 20, 0, 20]},     # low value, erratic
    ]


def test_returns_one_classification_per_sku():
    out = classify_portfolio(_items())
    assert len(out) == 4
    assert all(isinstance(c, SkuClassification) for c in out)


def test_abc_cut_by_cumulative_value():
    by_id = {c.product_id: c for c in classify_portfolio(_items())}
    assert by_id["A1"].abc == "A"
    assert by_id["A2"].abc == "A"
    assert by_id["B1"].abc == "B"
    assert by_id["C1"].abc == "C"


def test_xyz_by_coefficient_of_variation():
    by_id = {c.product_id: c for c in classify_portfolio(_items())}
    assert by_id["A1"].xyz == "X"          # cv 0
    assert by_id["A1"].cv == pytest.approx(0.0)
    assert by_id["C1"].xyz == "Z"          # cv > 1


def test_matrix_cell_combines_axes():
    by_id = {c.product_id: c for c in classify_portfolio(_items())}
    assert by_id["A1"].cell == "AX"
    assert by_id["C1"].cell == "CZ"


def test_service_level_target_follows_importance():
    by_id = {c.product_id: c for c in classify_portfolio(_items())}
    assert by_id["A1"].service_level == pytest.approx(0.98)
    assert by_id["B1"].service_level == pytest.approx(0.95)
    assert by_id["C1"].service_level == pytest.approx(0.90)


def test_cz_cell_recommends_make_to_order_or_review():
    by_id = {c.product_id: c for c in classify_portfolio(_items())}
    assert "review" in by_id["C1"].policy.lower() or "make-to-order" in by_id["C1"].policy.lower()


def test_z_class_uses_gamma_buffer():
    by_id = {c.product_id: c for c in classify_portfolio(_items())}
    assert by_id["C1"].buffer_distribution == "gamma"
    assert by_id["A1"].buffer_distribution == "normal"


def test_all_zero_demand_is_z_class():
    out = classify_portfolio([{"product_id": "Z9", "unit_cost": 1.0, "demand": [0, 0, 0, 0]}])
    assert out[0].xyz == "Z"
    assert math.isinf(out[0].cv)


def test_empty_portfolio_returns_empty():
    assert classify_portfolio([]) == []


def test_thresholds_are_configurable():
    # With a very low A-cut, only the top SKU is A.
    out = classify_portfolio(_items(), abc_thresholds=(0.5, 0.9))
    by_id = {c.product_id: c for c in out}
    assert by_id["A1"].abc == "A"
    assert by_id["A2"].abc == "B"  # pushed out of A by the tighter cut
