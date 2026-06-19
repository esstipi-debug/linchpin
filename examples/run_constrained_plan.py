"""The full chain: data source -> forecast -> policy -> business constraints.

Demonstrates the "AUTO" assembled end to end:
  1. pull demand from a pluggable source (CSV here; swap for SQL/API)
  2. forecast each SKU and derive an (s,Q) policy from sigma_e
  3. apply MOQ / case packs, then fit the whole portfolio under a budget cap

Usage:
    python examples/run_constrained_plan.py --budget 20000
    python examples/run_constrained_plan.py --data data/sample_demand.csv --budget 15000 --moq 50
"""

from __future__ import annotations

import argparse

from src.constraints import InventoryItem, allocate_under_budget, apply_order_rules, total_investment
from src.forecasting import forecast_demand
from src.policies import continuous_review_sq
from src.sources import CsvDemandSource


def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast + policy + constraints across a SKU portfolio.")
    parser.add_argument("--data", default="data/sample_demand.csv")
    parser.add_argument("--budget", type=float, default=20_000.0, help="max total inventory investment")
    parser.add_argument("--moq", type=float, default=0.0, help="minimum order quantity")
    parser.add_argument("--order-multiple", type=float, default=0.0, help="case-pack size")
    parser.add_argument("--service-level", type=float, default=0.95)
    parser.add_argument("--holding-rate", type=float, default=0.25)
    parser.add_argument("--order-cost", type=float, default=50.0)
    args = parser.parse_args()

    source = CsvDemandSource(args.data)
    items: list[InventoryItem] = []

    for product_id in source.list_products():
        series = source.demand_series(product_id)
        meta = source.metadata(product_id)

        forecast = forecast_demand(series)
        policy = continuous_review_sq(
            **forecast.to_engine_inputs(),
            holding_cost_per_unit=max(args.holding_rate * meta.mean_unit_cost, 1e-6),
            fixed_order_cost=args.order_cost,
            lead_time_periods=meta.lead_time_periods,
            cycle_service_level=args.service_level,
        )

        order_q = apply_order_rules(
            policy.order_quantity,
            minimum_order_quantity=args.moq,
            order_multiple=args.order_multiple,
        )
        items.append(
            InventoryItem(
                product_id=product_id,
                order_quantity=order_q,
                safety_stock=policy.safety_stock.safety_stock,
                unit_cost=meta.mean_unit_cost,
            )
        )

    print(f"Unconstrained investment: {total_investment(items):,.0f}  |  budget: {args.budget:,.0f}")
    plan = allocate_under_budget(items, args.budget)
    status = "OK" if plan.feasible else "INFEASIBLE (cycle stock alone over budget)"
    print(f"Safety-stock scale applied: {plan.safety_stock_scale:.2f}  ->  final: {plan.final_investment:,.0f}  [{status}]")
    print()
    for item in plan.items:
        print(f"  {item.product_id:8s}  Q={item.order_quantity:7.1f}  Ss={item.safety_stock:6.1f}  value={item.investment:,.0f}")


if __name__ == "__main__":
    main()
