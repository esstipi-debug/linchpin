"""Generate an 8-SKU demand portfolio for the Inventory Planner UI.

Writes data/sample_demand_portfolio.csv with 52 weekly periods per SKU. The mix
(stable / seasonal / intermittent) is chosen so the real engine auto-routes the
sparse SKUs to Croston and the rest to SES — i.e. the dashboard shows a realistic
spread of methods, biases, and statuses, all computed from this data.

Run: python scripts/generate_portfolio.py
"""

from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

N_WEEKS = 52
START = date(2024, 1, 1)

# id, mean, std, unit_cost, lead_time_days, kind
SKUS = [
    ("SKU-A", 96.0, 22.0, 50.0, 7, "stable"),
    ("SKU-B", 220.0, 48.0, 10.0, 14, "trend"),
    ("SKU-C", 12.0, 16.0, 120.0, 7, "intermittent"),
    ("SKU-D", 48.0, 8.0, 30.0, 7, "stable"),
    ("SKU-E", 310.0, 44.0, 6.0, 21, "seasonal"),
    ("SKU-F", 6.0, 9.0, 200.0, 14, "intermittent"),
    ("SKU-G", 78.0, 30.0, 45.0, 7, "noisy"),
    ("SKU-H", 140.0, 20.0, 18.0, 7, "stable"),
]


def series_for(mean: float, std: float, kind: str, rng: random.Random) -> list[int]:
    out: list[int] = []
    trend = rng.uniform(-0.004, 0.006) * mean
    phase = rng.uniform(0, math.tau)
    for i in range(N_WEEKS):
        if kind == "intermittent":
            occurs = rng.random() < 0.32
            val = max(0, round(mean / 0.32 + rng.gauss(0, std))) if occurs else 0
        else:
            season = math.sin((i / N_WEEKS) * math.tau + phase) * std * (0.45 if kind == "seasonal" else 0.25)
            drift = trend * i if kind in ("trend", "seasonal") else 0.0
            noise = rng.gauss(0, std * (0.9 if kind == "noisy" else 0.65))
            val = max(0, round(mean + drift + season + noise))
        out.append(val)
    return out


def main() -> None:
    rows = []
    for sku_id, mean, std, unit_cost, lead_days, kind in SKUS:
        rng = random.Random(hash(sku_id) & 0xFFFFFFFF)
        series = series_for(mean, std, kind, rng)
        for i, qty in enumerate(series):
            d = START + timedelta(weeks=i)
            rows.append([d.isoformat(), sku_id, qty, unit_cost, lead_days])

    out_path = Path(__file__).resolve().parents[1] / "data" / "sample_demand_portfolio.csv"
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "product_id", "quantity", "unit_cost", "lead_time_days"])
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows for {len(SKUS)} SKUs -> {out_path}")


if __name__ == "__main__":
    main()
