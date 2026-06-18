#!/usr/bin/env python3
"""Part III workflow: fill rate + cost optimization (Vandeput 2020, Ch. 7–8)."""

from __future__ import annotations

import argparse

from src.cost_optimization import compare_review_periods, optimize_rs_policy, optimize_sq_policy
from src.data_loader import annualize_demand, demand_stats, load_demand_csv
from src.fill_rate import fill_rate_from_inventory, safety_stock_for_fill_rate


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill rate and cost optimization (Ch. 7-8)")
    parser.add_argument("--data", default="data/sample_demand.csv")
    parser.add_argument("--product", default="SKU-A")
    parser.add_argument("--holding-cost", type=float, default=1.25, help="h per period (R,S) or per year (s,Q)")
    parser.add_argument("--order-cost", type=float, default=1000.0, help="k fixed order cost")
    parser.add_argument("--backorder-cost", type=float, default=50.0, help="b unit backorder cost")
    parser.add_argument("--lead-time", type=float, default=1.0)
    parser.add_argument("--lead-time-std", type=float, default=0.0)
    parser.add_argument("--fill-rate-target", type=float, default=0.98, help="Target fill rate beta")
    parser.add_argument("--periods-per-year", type=float, default=52.0)
    args = parser.parse_args()

    series = load_demand_csv(args.data, product_id=args.product)
    stats = demand_stats(series)
    mu = stats["mean_demand_per_period"]
    sigma = stats["demand_std_per_period"]
    annual_demand = annualize_demand(mu, args.periods_per_year)
    h_year = args.holding_cost * args.periods_per_year

    print(f"Product: {args.product}")
    print(f"Demand: mean={mu:.1f}/period, std={sigma:.1f}")
    print()

    # Ch. 7 — fill rate (bakery-style weekly policy)
    cycle_demand = mu  # R=1
    fr_target = safety_stock_for_fill_rate(cycle_demand, sigma, args.fill_rate_target)
    inventory = mu + fr_target.safety_stock
    fr_actual = fill_rate_from_inventory(inventory, cycle_demand, mu, sigma)

    print("--- Fill rate (Ch. 7) ---")
    print(f"Target beta: {args.fill_rate_target:.0%}")
    print(f"Safety stock for beta: {fr_target.safety_stock:.1f}")
    print(f"Cycle service level at beta: {fr_target.cycle_service_level:.0%}")
    print(f"Inventory at period start: {inventory:.1f}")
    print(f"Expected units short: {fr_actual.expected_units_short:.2f}")
    print(f"Achieved fill rate: {fr_actual.fill_rate:.1%}")
    print()

    # Ch. 8 — cost optimization (R,S) book example parameters by default
    print("--- Cost optimization (R,S) (Ch. 8.2) ---")
    comparison = compare_review_periods(
        mean_demand_per_period=mu,
        demand_std_per_period=sigma,
        mean_lead_time=args.lead_time,
        holding_cost_per_period=args.holding_cost,
        fixed_order_cost=args.order_cost,
        backorder_cost=args.backorder_cost,
        lead_time_std=args.lead_time_std,
    )
    print(comparison.to_string(index=False))
    best_rs = optimize_rs_policy(
        mean_demand_per_period=mu,
        demand_std_per_period=sigma,
        mean_lead_time=args.lead_time,
        holding_cost_per_period=args.holding_cost,
        fixed_order_cost=args.order_cost,
        backorder_cost=args.backorder_cost,
        lead_time_std=args.lead_time_std,
    )
    print()
    print(f"Optimal R = {best_rs.review_period:.0f}")
    print(f"Optimal alpha* = {best_rs.cost.cycle_service_level:.1%}")
    print(f"Fill rate at optimum = {best_rs.cost.fill_rate:.1%}")
    print(f"Cost per period = {best_rs.cost.total:.2f}")
    print(f"  holding={best_rs.cost.holding:.2f}, orders={best_rs.cost.transaction:.2f}, backorders={best_rs.cost.backorder:.2f}")
    print(f"S = {best_rs.order_up_to_level:.1f}")
    print()

    print("--- Cost optimization (s,Q) (Ch. 8.3) ---")
    best_sq = optimize_sq_policy(
        annual_demand=annual_demand,
        mean_demand_per_period=mu,
        demand_std_per_period=sigma,
        mean_lead_time=args.lead_time,
        holding_cost_per_year=h_year,
        fixed_order_cost=args.order_cost,
        backorder_cost=args.backorder_cost,
        lead_time_std=args.lead_time_std,
    )
    print(f"Optimal Q = {best_sq.order_quantity:.1f} (after {best_sq.iterations} iterations)")
    print(f"Optimal s = {best_sq.reorder_point:.1f}")
    print(f"Optimal alpha* = {best_sq.cost.cycle_service_level:.1%}")
    print(f"Cost per year = {best_sq.cost.total:.2f}")


if __name__ == "__main__":
    main()
