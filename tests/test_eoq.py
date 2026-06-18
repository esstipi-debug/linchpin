"""Tests for EOQ model."""

import math

import pytest

from src.eoq import compute_eoq, cost_ratio_vs_optimal, total_cost


def test_eoq_book_example():
    """Section 2.2.4: D=1000, k=50, h=1.75 -> Q* ~ 239."""
    result = compute_eoq(annual_demand=1000, holding_cost_per_unit=1.75, fixed_order_cost=50)
    assert result.order_quantity == pytest.approx(239, rel=0.01)
    assert result.optimal_total_cost == pytest.approx(418, rel=0.01)
    assert result.holding_cost == pytest.approx(result.transaction_cost, rel=0.01)


def test_cost_at_optimum_is_balanced():
    result = compute_eoq(500, 2.0, 100)
    assert result.holding_cost == pytest.approx(result.transaction_cost, rel=1e-9)


def test_sensitivity_ratio_symmetry():
    q_star = compute_eoq(1000, 1.75, 50).order_quantity
    ratio_high = cost_ratio_vs_optimal(q_star * math.sqrt(2), q_star)
    ratio_low = cost_ratio_vs_optimal(q_star / math.sqrt(2), q_star)
    assert ratio_high == pytest.approx(ratio_low, rel=1e-9)
    assert ratio_high == pytest.approx(1.06, rel=0.01)


def test_total_cost_matches_components():
    q = 200
    d, h, k = 1000, 1.75, 50
    assert total_cost(q, d, h, k) == pytest.approx(k * d / q + h * q / 2)
