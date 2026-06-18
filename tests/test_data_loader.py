"""Tests for data_loader metadata."""

import pytest

from src.data_loader import list_products, product_metadata


def test_list_products_sample():
    products = list_products("data/sample_demand.csv")
    assert "SKU-A" in products
    assert "SKU-B" in products


def test_lead_time_from_csv():
    meta = product_metadata("data/sample_demand.csv", "SKU-A", periods_per_year=52)
    assert meta.lead_time_periods == pytest.approx(7 * 52 / 365, rel=0.01)
    assert meta.mean_unit_cost == 50.0
