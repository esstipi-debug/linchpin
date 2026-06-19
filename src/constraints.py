"""Business constraints — the gap between a textbook policy and a real plan.

The models compute an *unconstrained* optimum: order Q*, hold safety stock Ss.
Reality adds limits the math ignores: suppliers enforce minimum order quantities
and case packs, perishables can't be over-ordered, and the warehouse / budget
can't hold every SKU's ideal stock at once.

This module adjusts engine output to respect those limits:
  - per-order   : MOQ, order multiples (case packs), shelf-life cap
  - portfolio   : a budget allocator that trims safety stock across SKUs to fit
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace


def round_up_to_multiple(quantity: float, multiple: float) -> float:
    """Round quantity up to the nearest positive multiple (case pack)."""
    if multiple <= 0:
        return quantity
    return math.ceil(quantity / multiple) * multiple


def apply_order_rules(
    quantity: float,
    *,
    minimum_order_quantity: float = 0.0,
    order_multiple: float = 0.0,
    max_quantity: float | None = None,
) -> float:
    """Apply MOQ, case-pack rounding, then an upper cap, in that order."""
    q = max(quantity, minimum_order_quantity)
    q = round_up_to_multiple(q, order_multiple)
    if max_quantity is not None:
        q = min(q, max_quantity)
    return q


def shelf_life_max_quantity(demand_per_period: float, shelf_life_periods: float) -> float:
    """Largest order consumable before expiry: demand_rate * shelf_life."""
    if demand_per_period < 0 or shelf_life_periods < 0:
        raise ValueError("demand_per_period and shelf_life_periods must be >= 0")
    return demand_per_period * shelf_life_periods


@dataclass(frozen=True)
class InventoryItem:
    """One SKU's stock position, used for portfolio-level constraints."""

    product_id: str
    order_quantity: float
    safety_stock: float
    unit_cost: float

    @property
    def cycle_investment(self) -> float:
        """Value of average cycle stock (Q/2) — the economic floor."""
        return (self.order_quantity / 2.0) * self.unit_cost

    @property
    def safety_investment(self) -> float:
        return max(self.safety_stock, 0.0) * self.unit_cost

    @property
    def investment(self) -> float:
        return self.cycle_investment + self.safety_investment


def total_investment(items: list[InventoryItem]) -> float:
    return sum(item.investment for item in items)


@dataclass(frozen=True)
class BudgetAllocation:
    """Result of fitting a portfolio under a budget cap."""

    items: list[InventoryItem]
    feasible: bool
    safety_stock_scale: float
    requested_investment: float
    final_investment: float


def allocate_under_budget(items: list[InventoryItem], budget: float) -> BudgetAllocation:
    """
    Trim safety stock proportionally so total inventory investment fits ``budget``.

    Cycle stock (Q/2) is the economic order floor and is preserved; only safety
    stock is reduced. If even zero safety stock exceeds the budget, the result is
    flagged infeasible (cycle stock alone is over budget).
    """
    if budget < 0:
        raise ValueError("budget must be >= 0")

    requested = total_investment(items)
    cycle_floor = sum(item.cycle_investment for item in items)
    safety_total = sum(item.safety_investment for item in items)

    if requested <= budget:
        return BudgetAllocation(items, True, 1.0, requested, requested)

    if budget < cycle_floor or safety_total <= 0:
        zeroed = [replace(item, safety_stock=0.0) for item in items]
        return BudgetAllocation(zeroed, budget >= cycle_floor, 0.0, requested, cycle_floor)

    scale = (budget - cycle_floor) / safety_total
    adjusted = [replace(item, safety_stock=item.safety_stock * scale) for item in items]
    return BudgetAllocation(adjusted, True, scale, requested, total_investment(adjusted))
