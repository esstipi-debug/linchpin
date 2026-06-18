"""Tests for volume discount EOQ — Vandeput (2020), Section 2.5.3."""

import pytest

from src.eoq import PriceBreak, compute_eoq_volume_discount


def test_volume_discount_picks_cheaper_tier():
    breaks = [
        PriceBreak(0, 10.0),
        PriceBreak(200, 9.0),
        PriceBreak(500, 8.5),
    ]
    result = compute_eoq_volume_discount(
        annual_demand=1200,
        holding_cost_rate=0.25,
        fixed_order_cost=100,
        price_breaks=breaks,
    )
    assert result.order_quantity >= breaks[result.price_break_index].min_quantity
    assert result.optimal_total_cost > 0


def test_single_break_matches_eoq():
    breaks = [PriceBreak(0, 5.0)]
    vd = compute_eoq_volume_discount(1000, 0.2, 50, breaks)
    from src.eoq import compute_eoq

    plain = compute_eoq(1000, 0.2 * 5.0, 50)
    assert vd.order_quantity == pytest.approx(plain.order_quantity, rel=0.01)
