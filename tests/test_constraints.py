"""Tests for business constraints (MOQ, shelf life, budget allocation)."""

import pytest

from src.constraints import (
    BudgetAllocation,
    InventoryItem,
    allocate_under_budget,
    apply_order_rules,
    round_up_to_multiple,
    shelf_life_max_quantity,
    total_investment,
)


def test_round_up_to_multiple():
    assert round_up_to_multiple(101, 25) == 125
    assert round_up_to_multiple(100, 25) == 100
    assert round_up_to_multiple(101, 0) == 101  # no case pack


def test_apply_order_rules_moq_then_pack_then_cap():
    # MOQ raises 30 -> 50, case pack of 12 rounds 50 -> 60, cap 55 trims -> 55
    assert apply_order_rules(30, minimum_order_quantity=50, order_multiple=12, max_quantity=55) == 55
    # below MOQ, no cap
    assert apply_order_rules(10, minimum_order_quantity=24) == 24
    # plain quantity untouched
    assert apply_order_rules(100) == 100


def test_shelf_life_max_quantity():
    assert shelf_life_max_quantity(20, 6) == 120
    with pytest.raises(ValueError):
        shelf_life_max_quantity(-1, 6)


def test_inventory_item_investment_splits_cycle_and_safety():
    item = InventoryItem("SKU-A", order_quantity=200, safety_stock=40, unit_cost=5)
    assert item.cycle_investment == pytest.approx(200 / 2 * 5)  # 500
    assert item.safety_investment == pytest.approx(40 * 5)  # 200
    assert item.investment == pytest.approx(700)


def test_allocate_under_budget_no_change_when_within():
    items = [InventoryItem("A", 100, 20, 2), InventoryItem("B", 200, 10, 1)]
    result = allocate_under_budget(items, budget=10_000)
    assert isinstance(result, BudgetAllocation)
    assert result.feasible
    assert result.safety_stock_scale == 1.0
    assert result.items == items


def test_allocate_under_budget_scales_safety_stock_to_fit():
    items = [InventoryItem("A", 200, 100, 1), InventoryItem("B", 200, 100, 1)]
    # cycle floor = (100 + 100) = 200; safety = 200; total = 400
    result = allocate_under_budget(items, budget=300)
    assert result.feasible
    assert result.safety_stock_scale == pytest.approx(0.5)
    assert result.final_investment == pytest.approx(300)
    assert total_investment(result.items) == pytest.approx(300)


def test_allocate_under_budget_infeasible_when_cycle_floor_exceeds():
    items = [InventoryItem("A", 200, 50, 1)]  # cycle floor = 100
    result = allocate_under_budget(items, budget=80)
    assert result.feasible is False
    assert result.items[0].safety_stock == 0.0
    assert result.final_investment == pytest.approx(100)  # cycle floor


def test_allocate_under_budget_rejects_negative_budget():
    with pytest.raises(ValueError):
        allocate_under_budget([InventoryItem("A", 10, 1, 1)], budget=-1)
