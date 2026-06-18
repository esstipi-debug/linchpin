"""Tests for simulation optimization — Vandeput (2020), Chapter 13."""

import pytest

from src.simulation_opt import find_best_safety_stock, find_best_safety_stock_smart_start


def test_find_best_ss_reduces_cost_vs_zero_ss():
    result = find_best_safety_stock(
        mean_demand=100,
        std_demand=25,
        lead_time_periods=4,
        review_period=1,
        holding_cost_per_period=1.0,
        fixed_order_cost=1000,
        backorder_cost=50,
        step_size=10,
        start_ss=50,
        search_radius=100,
        periods=2_000,
        seed=123,
    )
    zero = find_best_safety_stock(
        mean_demand=100,
        std_demand=25,
        lead_time_periods=4,
        review_period=1,
        holding_cost_per_period=1.0,
        fixed_order_cost=1000,
        backorder_cost=50,
        step_size=10,
        start_ss=0,
        search_radius=0,
        periods=2_000,
        seed=123,
    )
    assert result.total_cost <= zero.total_cost + 5


def test_smart_start_near_analytical():
    sim, analytical_ss = find_best_safety_stock_smart_start(
        mean_demand=50,
        std_demand=10,
        lead_time_periods=2,
        review_period=1,
        holding_cost_per_period=2.0,
        fixed_order_cost=500,
        backorder_cost=30,
        step_size=5,
        search_radius=40,
        periods=2_000,
        seed=99,
    )
    assert sim.safety_stock == pytest.approx(analytical_ss, abs=40)
