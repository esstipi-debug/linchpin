"""Pluggable demand data sources — decouple the engine from any one backend.

The models used to read demand straight from a CSV path. Real deployments pull
demand from a database, an ERP/WMS export, or an API response. This module puts
a single ``DemandSource`` interface in front of all of them, so swapping CSV for
SQL/API later means writing one adapter — not touching the engine.

Built-in adapters:
  - ``CsvDemandSource``       : a demand CSV on disk (today's default)
  - ``DataFrameDemandSource`` : an in-memory DataFrame (SQL/API results)

A future ``SqlDemandSource`` / ``ErpDemandSource`` only needs to satisfy the
``DemandSource`` protocol: ``list_products``, ``demand_series``, ``metadata``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

from src.data_loader import ProductMetadata

REQUIRED_COLUMNS = {"date", "product_id", "quantity"}


@runtime_checkable
class DemandSource(Protocol):
    """Any backend that can yield demand history and product metadata."""

    def list_products(self) -> list[str]: ...

    def demand_series(self, product_id: str) -> np.ndarray: ...

    def metadata(self, product_id: str) -> ProductMetadata: ...


def _validate_frame(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {missing}")
    return df.sort_values(["product_id", "date"])


def _series_from_frame(df: pd.DataFrame, product_id: str) -> np.ndarray:
    sku = df[df["product_id"] == product_id]
    if sku.empty:
        raise ValueError(f"no rows for product_id={product_id!r}")
    return sku["quantity"].astype(float).to_numpy()


def _metadata_from_frame(
    df: pd.DataFrame,
    product_id: str,
    *,
    periods_per_year: float,
    default_lead_time_periods: float,
) -> ProductMetadata:
    sku = df[df["product_id"] == product_id]
    if sku.empty:
        raise ValueError(f"no rows for product_id={product_id!r}")

    values = sku["quantity"].astype(float).to_numpy()
    mu = float(np.mean(values))
    sigma = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0

    unit_cost = float(sku["unit_cost"].astype(float).mean()) if "unit_cost" in sku.columns else 1.0

    if "lead_time_days" in sku.columns:
        lt_periods = float(sku["lead_time_days"].astype(float).median()) * periods_per_year / 365.0
    else:
        lt_periods = default_lead_time_periods

    return ProductMetadata(
        product_id=product_id,
        mean_demand_per_period=mu,
        demand_std_per_period=sigma,
        periods=len(values),
        mean_unit_cost=unit_cost,
        lead_time_periods=lt_periods,
    )


class _FrameDemandSource:
    """Shared implementation backed by a validated DataFrame."""

    def __init__(
        self,
        frame: pd.DataFrame,
        *,
        periods_per_year: float = 52.0,
        default_lead_time_periods: float = 2.0,
    ) -> None:
        self._df = _validate_frame(frame)
        self._periods_per_year = periods_per_year
        self._default_lead_time_periods = default_lead_time_periods

    def list_products(self) -> list[str]:
        return sorted(self._df["product_id"].unique().tolist())

    def demand_series(self, product_id: str) -> np.ndarray:
        return _series_from_frame(self._df, product_id)

    def metadata(self, product_id: str) -> ProductMetadata:
        return _metadata_from_frame(
            self._df,
            product_id,
            periods_per_year=self._periods_per_year,
            default_lead_time_periods=self._default_lead_time_periods,
        )


class DataFrameDemandSource(_FrameDemandSource):
    """Demand source backed by an in-memory DataFrame (e.g. SQL/API results)."""


class CsvDemandSource(_FrameDemandSource):
    """Demand source backed by a CSV file on disk."""

    def __init__(
        self,
        path: str,
        *,
        periods_per_year: float = 52.0,
        default_lead_time_periods: float = 2.0,
    ) -> None:
        frame = pd.read_csv(path, parse_dates=["date"])
        super().__init__(
            frame,
            periods_per_year=periods_per_year,
            default_lead_time_periods=default_lead_time_periods,
        )
