"""Load demand history and compute per-period statistics."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_demand_csv(
    path: str | Path,
    *,
    product_id: str | None = None,
    quantity_col: str = "quantity",
    date_col: str = "date",
    product_col: str = "product_id",
) -> pd.Series:
    """Return a time-ordered demand series for one SKU."""
    df = pd.read_csv(path, parse_dates=[date_col])
    if product_id is not None:
        df = df[df[product_col] == product_id]
    if df.empty:
        raise ValueError(f"no rows for product_id={product_id!r}")
    df = df.sort_values(date_col)
    return df[quantity_col].astype(float)


def demand_stats(series: pd.Series) -> dict[str, float]:
    """Mean and sample std (ddof=1) per period."""
    values = series.to_numpy(dtype=float)
    return {
        "mean_demand_per_period": float(np.mean(values)),
        "demand_std_per_period": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "periods": float(len(values)),
    }


def annualize_demand(mean_per_period: float, periods_per_year: float) -> float:
    return mean_per_period * periods_per_year
