"""Tests for newsvendor — Vandeput (2020), Chapter 11."""

import pytest

from src.newsvendor import (
    critical_ratio,
    muffin_pmf,
    optimal_newsvendor_discrete,
)


def test_muffin_critical_ratio():
    # price=6, cost=2, salvage=1 -> cu=4, co=1 -> cr=0.8
    cr = critical_ratio(4, 1)
    assert cr == pytest.approx(0.8)


def test_muffin_optimal_quantity():
    pmf = muffin_pmf()
    result = optimal_newsvendor_discrete(
        pmf,
        price=6.0,
        unit_cost=2.0,
        salvage_value=1.0,
    )
    assert result.optimal_quantity == 4
    assert result.critical_ratio == pytest.approx(0.8)
    assert result.expected_profit == pytest.approx(6.0, abs=0.1)


def test_muffin_profit_at_q4():
    pmf = muffin_pmf()
    from src.newsvendor import expected_profit_discrete

    p4 = expected_profit_discrete(4, pmf, 6, 2, salvage_value=1)
    p6 = expected_profit_discrete(6, pmf, 6, 2, salvage_value=1)
    assert p4 == pytest.approx(6.0, abs=0.1)
    assert p6 == pytest.approx(6.0, abs=0.1)
