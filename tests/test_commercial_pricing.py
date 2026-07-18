"""Tests for src/commercial_pricing.py: Kern's own GMV-band quote engine.

This is what Kern CHARGES a customer for a package (Starter/Growth/Scale/
Retainer) - not to be confused with src/pricing.py, jobs/repricing.py, or
src/pricing_intel/, which price the CLIENT's own product catalog.

Primary axis: package_key (1:1 with a revenue band). base_price and the SKU
fairness rule are looked up by package_key, NEVER by annual_revenue -
annual_revenue only suggests a better-fitting package and flags a mismatch
when the requested package doesn't match the declared revenue band. See
docs/superpowers/plans/2026-07-18-kern-gmv-band-gtm.md Part 2 "Primary-axis
resolution" for the resolved design rationale (this file's tests exist
because a prior adversarial review flagged that ambiguity as worth pinning
down in code, not just prose).
"""
from __future__ import annotations

import pytest

from src.commercial_pricing import (
    UNBANDED,
    PriceQuote,
    RevenueBand,
    SkuFairnessRule,
    quote_price,
    render_price_string,
)

# ---- brief's example tests (verbatim) -----------------------------------------


def test_starter_floor_at_band_base():
    q = quote_price("starter", annual_revenue=2_000_000, sku_count=400)
    assert q.monthly_price == 900.0          # <= included SKUs -> no fairness add
    assert q.ceiling_hit is False


def test_starter_fairness_block_added():
    q = quote_price("starter", annual_revenue=2_000_000, sku_count=1_000)
    assert q.fairness_adjustment == 80.0     # ceil((1000-500)/250)=2 blocks * 40
    assert q.monthly_price == 980.0


def test_starter_ceiling_clamps():
    q = quote_price("starter", annual_revenue=2_000_000, sku_count=100_000)
    assert q.monthly_price == 1500.0         # clamped to Starter ceiling
    assert q.ceiling_hit is True


def test_scale_is_flat_no_fairness():
    q = quote_price("scale", annual_revenue=10_000_000, sku_count=50_000)
    assert q.monthly_price == 3200.0
    assert q.fairness_adjustment == 0.0


def test_invalid_package_raises():
    with pytest.raises(ValueError):
        quote_price("nonexistent", annual_revenue=1_000_000)


# ---- growth mirrors starter's fairness shape -----------------------------------


def test_growth_floor_at_band_base():
    q = quote_price("growth", annual_revenue=5_000_000, sku_count=1_500)
    assert q.monthly_price == 1500.0
    assert q.fairness_adjustment == 0.0
    assert q.ceiling_hit is False


def test_growth_fairness_block_added():
    q = quote_price("growth", annual_revenue=5_000_000, sku_count=3_000)
    # ceil((3000-2000)/500) = 2 blocks * 60 = 120
    assert q.fairness_adjustment == 120.0
    assert q.monthly_price == 1620.0


def test_growth_ceiling_clamps():
    q = quote_price("growth", annual_revenue=5_000_000, sku_count=1_000_000)
    assert q.monthly_price == 3200.0
    assert q.ceiling_hit is True


def test_retainer_is_flat_and_unbanded():
    q = quote_price("retainer", annual_revenue=5_000_000, sku_count=999_999)
    assert q.monthly_price == 4500.0
    assert q.fairness_adjustment == 0.0
    assert q.ceiling_hit is False
    assert q.revenue_band_key == UNBANDED
    assert q.suggested_package_key is None
    assert q.revenue_band_match is True


# ---- sku_count=None edge case ---------------------------------------------------


def test_sku_count_none_means_no_fairness_adjustment():
    q = quote_price("starter", annual_revenue=2_000_000, sku_count=None)
    assert q.sku_count is None
    assert q.fairness_adjustment == 0.0
    assert q.monthly_price == 900.0
    assert q.ceiling_hit is False


# ---- band boundary revenue -------------------------------------------------------


def test_band_boundary_revenue_belongs_to_the_higher_band():
    # Starter's band is [1M, 3M) and Growth's is [3M, 8M) - a half-open
    # convention, so exactly 3,000,000 belongs to Growth, not Starter.
    q_growth = quote_price("growth", annual_revenue=3_000_000, sku_count=10)
    assert q_growth.revenue_band_match is True

    q_starter = quote_price("starter", annual_revenue=3_000_000, sku_count=10)
    assert q_starter.revenue_band_match is False
    assert q_starter.suggested_package_key == "growth"
    # base_price still comes from package_key, not annual_revenue.
    assert q_starter.monthly_price == 900.0


def test_growth_scale_boundary_revenue_belongs_to_scale():
    q = quote_price("scale", annual_revenue=8_000_000, sku_count=10)
    assert q.revenue_band_match is True

    q_growth = quote_price("growth", annual_revenue=8_000_000, sku_count=10)
    assert q_growth.revenue_band_match is False
    assert q_growth.suggested_package_key == "scale"


# ---- mismatch detection: package_key is the source of truth for price ----------


def test_package_mismatch_does_not_silently_override_base_price():
    # A Growth/Scale-sized revenue quoted against "starter" must NOT silently
    # charge the Growth/Scale price - it returns the Starter price and
    # surfaces the mismatch via suggested_package_key instead.
    q = quote_price("starter", annual_revenue=10_000_000)
    assert q.monthly_price == 900.0
    assert q.revenue_band_match is False
    assert q.suggested_package_key == "scale"
    assert q.needs_clarification is False


def test_scale_quoted_with_low_revenue_keeps_scale_price_and_suggests_starter():
    q = quote_price("scale", annual_revenue=1_500_000)
    assert q.monthly_price == 3200.0
    assert q.revenue_band_match is False
    assert q.suggested_package_key == "starter"


# ---- below the lowest band: needs_clarification, never a silent clamp ----------


def test_revenue_below_lowest_band_needs_clarification():
    q = quote_price("starter", annual_revenue=500_000, sku_count=100)
    assert q.needs_clarification is True
    assert q.suggested_package_key is None          # no existing band fits below $1M
    assert q.revenue_band_match is False
    # package_key remains the source of truth for price - no silent clamp.
    assert q.monthly_price == 900.0


def test_zero_revenue_needs_clarification():
    q = quote_price("growth", annual_revenue=0.0)
    assert q.needs_clarification is True
    assert q.monthly_price == 1500.0


def test_retainer_with_sub_band_revenue_still_flags_needs_clarification():
    # Retainer itself has no band (revenue_band_match is trivially True), but
    # needs_clarification is about the declared revenue itself, independent
    # of which package_key was requested.
    q = quote_price("retainer", annual_revenue=200_000)
    assert q.needs_clarification is True
    assert q.revenue_band_match is True
    assert q.monthly_price == 4500.0


# ---- validation ------------------------------------------------------------------


def test_negative_annual_revenue_raises():
    with pytest.raises(ValueError):
        quote_price("starter", annual_revenue=-1.0)


def test_negative_sku_count_raises():
    with pytest.raises(ValueError):
        quote_price("starter", annual_revenue=2_000_000, sku_count=-5)


def test_non_finite_annual_revenue_raises():
    with pytest.raises(ValueError):
        quote_price("starter", annual_revenue=float("nan"))


# ---- dataclass shape sanity (documents the interface, not just quote_price) ----


def test_revenue_band_dataclass_is_frozen():
    band = RevenueBand(
        key="starter_band", label="USD 1,000,000-3,000,000/yr",
        min_annual_revenue=1_000_000.0, max_annual_revenue=3_000_000.0,
        base_price=900.0,
    )
    with pytest.raises(Exception):
        band.base_price = 1.0  # type: ignore[misc]


def test_sku_fairness_rule_dataclass_is_frozen():
    rule = SkuFairnessRule(included_skus=500, block_size=250, block_increment=40.0, ceiling=1500.0)
    with pytest.raises(Exception):
        rule.ceiling = 1.0  # type: ignore[misc]


def test_price_quote_is_frozen():
    q = quote_price("starter", annual_revenue=2_000_000, sku_count=400)
    assert isinstance(q, PriceQuote)
    with pytest.raises(Exception):
        q.monthly_price = 1.0  # type: ignore[misc]


# ---- render_price_string ---------------------------------------------------------


def test_render_price_string_contains_the_monthly_price():
    q = quote_price("starter", annual_revenue=2_000_000, sku_count=1_000)
    text = render_price_string(q)
    assert "980" in text


def test_render_price_string_flags_mismatch():
    q = quote_price("starter", annual_revenue=10_000_000)
    text = render_price_string(q)
    assert "scale" in text.lower()


def test_render_price_string_flags_needs_clarification():
    q = quote_price("starter", annual_revenue=500_000)
    text = render_price_string(q)
    assert "1,000,000" in text or "1000000" in text
