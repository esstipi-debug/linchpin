"""Tests for pluggable demand data sources."""

import numpy as np
import pandas as pd
import pytest

from src.sources import (
    CsvDemandSource,
    DataFrameDemandSource,
    DemandSource,
)


def _frame():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01", "2024-01-08", "2024-01-01", "2024-01-08"]),
            "product_id": ["SKU-A", "SKU-A", "SKU-B", "SKU-B"],
            "quantity": [100, 120, 40, 60],
            "unit_cost": [50, 50, 10, 10],
            "lead_time_days": [7, 7, 14, 14],
        }
    )


def test_dataframe_source_lists_and_returns_series():
    src = DataFrameDemandSource(_frame())
    assert src.list_products() == ["SKU-A", "SKU-B"]
    np.testing.assert_array_equal(src.demand_series("SKU-A"), np.array([100.0, 120.0]))


def test_dataframe_source_metadata():
    src = DataFrameDemandSource(_frame())
    meta = src.metadata("SKU-B")
    assert meta.product_id == "SKU-B"
    assert meta.mean_demand_per_period == pytest.approx(50.0)
    assert meta.mean_unit_cost == pytest.approx(10.0)
    # 14 days * 52 / 365 ~ 1.99 periods
    assert meta.lead_time_periods == pytest.approx(14 * 52 / 365)


def test_dataframe_source_rejects_missing_columns():
    with pytest.raises(ValueError):
        DataFrameDemandSource(pd.DataFrame({"date": [], "product_id": []}))


def test_unknown_product_raises():
    src = DataFrameDemandSource(_frame())
    with pytest.raises(ValueError):
        src.demand_series("SKU-Z")


def test_csv_source_reads_sample_data():
    src = CsvDemandSource("data/sample_demand.csv")
    assert isinstance(src, DemandSource)  # satisfies the protocol
    products = src.list_products()
    assert len(products) >= 1
    series = src.demand_series(products[0])
    assert series.ndim == 1 and len(series) > 0


def test_sources_are_interchangeable():
    """CSV and DataFrame backends expose the identical interface."""
    df_src = DataFrameDemandSource(_frame())
    assert isinstance(df_src, DemandSource)
    assert hasattr(df_src, "list_products")
    assert hasattr(df_src, "demand_series")
    assert hasattr(df_src, "metadata")
