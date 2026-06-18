"""Tests for inventory simulations."""

from src.simulation import simulate_rs_policy, simulate_sq_policy


def test_rs_simulation_runs():
    result = simulate_rs_policy(
        order_up_to_level=150,
        lead_time_periods=2,
        review_period=4,
        periods=5000,
        mean_demand=10,
        std_demand=5,
        seed=1,
    )
    assert 0 <= result.simulated_cycle_service_level <= 1
    assert result.mean_on_hand > 0


def test_sq_simulation_runs():
    result = simulate_sq_policy(
        reorder_point=30,
        order_quantity=50,
        lead_time_periods=2,
        periods=5000,
        mean_demand=10,
        std_demand=5,
        seed=1,
    )
    assert 0 <= result.simulated_period_service_level <= 1
    assert result.mean_order_quantity > 0


def test_high_service_target_increases_on_hand():
    low = simulate_rs_policy(120, 2, 4, periods=3000, mean_demand=10, std_demand=5, seed=2)
    high = simulate_rs_policy(200, 2, 4, periods=3000, mean_demand=10, std_demand=5, seed=2)
    assert high.mean_on_hand > low.mean_on_hand
