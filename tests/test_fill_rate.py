"""Tests for fill rate model — Vandeput (2020), Chapter 7."""

import pytest

from src.fill_rate import (
    fill_rate_from_inventory,
    inverse_standard_loss,
    normal_loss,
    normal_loss_standard,
    safety_stock_for_fill_rate,
)


def test_bakery_example_section_7_3():
    """Flour: mu=250, sigma=30, inv=270 -> Us~4.53, beta~98%."""
    inv, mu, std = 270, 250, 30
    lost = normal_loss(inv, mu, std)
    assert lost == pytest.approx(4.53, abs=0.1)
    fr = fill_rate_from_inventory(inv, 250, mu, std)
    assert fr.fill_rate == pytest.approx(0.98, abs=0.01)


def test_cycle_sl_vs_fill_rate_gap():
    """High fill rate can coexist with low cycle SL (Section 7.3.1)."""
    inv, mu, std = 270, 250, 30
    fr = fill_rate_from_inventory(inv, 250, mu, std)
    assert fr.fill_rate > 0.95
    assert fr.cycle_service_level < 0.80


def test_inverse_loss_solver_vs_polynomial():
    target = 0.05
    z_poly = inverse_standard_loss(target, use_solver=False)
    z_solver = inverse_standard_loss(target, use_solver=True)
    assert z_poly == pytest.approx(z_solver, abs=0.02)
    assert z_poly == pytest.approx(1.256, abs=0.02)


def test_safety_stock_for_98_percent_fill_rate():
    """Section 7.3.2 bakery: beta=98% -> Ss~18.3."""
    result = safety_stock_for_fill_rate(cycle_demand=250, demand_std_risk=30, target_fill_rate=0.98)
    assert result.safety_stock == pytest.approx(18.3, abs=0.5)
    assert result.cycle_service_level == pytest.approx(0.73, abs=0.03)


def test_normal_loss_standard_at_zero():
    val = float(normal_loss_standard(0))
    assert val == pytest.approx(0.399, abs=0.01)
