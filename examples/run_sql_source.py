"""Live-data demo: read demand from a SQL database, not a CSV export.

Stands in for an ERP/WMS feed. We seed an in-memory SQLite table from the
sample CSV, then run the exact same chain — source -> forecast -> policy —
through ``SqlDemandSource``. Swapping SQLite for Postgres/MySQL is just a
different DB-API connection; nothing downstream changes.

Usage:
    python examples/run_sql_source.py
    python examples/run_sql_source.py --data data/sample_demand.csv --service-level 0.95
"""

from __future__ import annotations

import argparse
import sqlite3

import pandas as pd

from src.forecasting import forecast_demand
from src.policies import continuous_review_sq
from src.sources import SqlDemandSource


def seed_database(csv_path: str) -> sqlite3.Connection:
    """Load the sample CSV into an in-memory SQLite 'demand' table."""
    conn = sqlite3.connect(":memory:")
    df = pd.read_csv(csv_path)
    df.to_sql("demand", conn, index=False, if_exists="replace")
    return conn


def main() -> None:
    parser = argparse.ArgumentParser(description="Forecast + policy from a live SQL demand source.")
    parser.add_argument("--data", default="data/sample_demand.csv")
    parser.add_argument("--service-level", type=float, default=0.95)
    parser.add_argument("--holding-rate", type=float, default=0.25)
    parser.add_argument("--order-cost", type=float, default=50.0)
    args = parser.parse_args()

    conn = seed_database(args.data)
    try:
        source = SqlDemandSource(conn, table="demand")
        print(f"Live SQL source: {len(source.list_products())} SKUs in table 'demand'\n")

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
            print(f"  {product_id:8s}  forecast={forecast.forecast:6.1f}/period  "
                  f"Q*={policy.order_quantity:6.1f}  reorder={policy.reorder_point:6.1f}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
