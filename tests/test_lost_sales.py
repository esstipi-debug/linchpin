"""Tests for lost sales simulation — Vandeput (2020), Section 5.3.2."""

from src.simulation import simulate_rs_policy


def test_lost_sales_more_stockouts_than_backorders():
    kwargs = dict(
        order_up_to_level=200,
        lead_time_periods=2,
        review_period=1,
        mean_demand=100,
        std_demand=25,
        periods=3000,
        seed=7,
    )
    backorders = simulate_rs_policy(**kwargs, lost_sales=False)
    lost = simulate_rs_policy(**kwargs, lost_sales=True)
    assert lost.stockout_periods >= backorders.stockout_periods
