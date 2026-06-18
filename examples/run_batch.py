#!/usr/bin/env python3
"""Analyze all SKUs in demand CSV and export summary."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.batch import BatchConfig, run_batch_analysis


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch inventory analysis for all SKUs")
    parser.add_argument("--data", type=Path, default=Path("data/sample_demand.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/batch_summary.csv"))
    parser.add_argument("--holding-rate", type=float, default=0.25, help="h as fraction of unit cost")
    parser.add_argument("--order-cost", type=float, default=1000.0)
    parser.add_argument("--service-level", type=float, default=0.95)
    args = parser.parse_args()

    config = BatchConfig(
        holding_cost_rate=args.holding_rate,
        fixed_order_cost=args.order_cost,
        service_level=args.service_level,
    )
    df = run_batch_analysis(args.data, args.output, config)
    print(f"Analyzed {len(df)} products -> {args.output}")
    print(df[["product_id", "eoq_Q", "sq_s", "rs_S", "optimal_R", "distribution"]].to_string(index=False))


if __name__ == "__main__":
    main()
