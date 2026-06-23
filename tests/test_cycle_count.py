"""Tests for cycle-count planning (plan §2.4).

Counts by ABC class (A counted often, C rarely), spread evenly across the working year,
with a balanced daily load. Pure - no deps. Composes with classification.py output
(anything exposing .product_id and .abc).
"""

import pytest

from src.cycle_count import (
    DEFAULT_POLICY,
    CountItem,
    CountPolicy,
    CountTask,
    annual_workload,
    build_schedule,
    count_frequency,
    daily_load,
)


def test_count_frequency_by_class_with_unknown_zero():
    assert count_frequency(DEFAULT_POLICY, "A") == 12
    assert count_frequency(DEFAULT_POLICY, "B") == 4
    assert count_frequency(DEFAULT_POLICY, "C") == 1
    assert count_frequency(DEFAULT_POLICY, "Z") == 0


def test_annual_workload_totals_by_class():
    items = [CountItem("a1", "A"), CountItem("a2", "A"), CountItem("b1", "B"), CountItem("c1", "C")]

    wl = annual_workload(items)

    assert wl["A"] == 24
    assert wl["B"] == 4
    assert wl["C"] == 1
    assert wl["total"] == 29


def test_schedule_has_one_task_per_required_count():
    schedule = build_schedule([CountItem("a1", "A")], working_days=250)

    assert all(isinstance(t, CountTask) for t in schedule)
    assert len(schedule) == 12
    assert {t.product_id for t in schedule} == {"a1"}


def test_schedule_days_are_in_range_sorted_and_spread():
    schedule = build_schedule([CountItem("a1", "A")], working_days=250)

    days = [t.day for t in schedule]
    assert days == sorted(days)
    assert days[0] == 0
    assert all(0 <= d < 250 for d in days)
    assert len(set(days)) == 12  # evenly spread -> distinct days


def test_daily_load_sums_to_total_workload():
    items = [CountItem("a1", "A"), CountItem("b1", "B"), CountItem("c1", "C")]
    schedule = build_schedule(items, working_days=250)

    load = daily_load(schedule, working_days=250)

    assert len(load) == 250
    assert sum(load) == annual_workload(items)["total"]


def test_unknown_class_schedules_no_counts():
    assert build_schedule([CountItem("x", "Z")], working_days=250) == []


def test_empty_items_yield_empty_schedule():
    assert build_schedule([], working_days=250) == []
    assert annual_workload([])["total"] == 0


def test_invalid_working_days_raises():
    with pytest.raises(ValueError):
        build_schedule([CountItem("a1", "A")], working_days=0)


def test_custom_policy_overrides_frequencies():
    policy = CountPolicy({"A": 52, "B": 12, "C": 2})

    assert count_frequency(policy, "A") == 52
    assert len(build_schedule([CountItem("a1", "A")], policy, working_days=260)) == 52


def test_accepts_any_item_with_product_id_and_abc():
    class Row:  # SkuClassification-shaped duck type
        def __init__(self, pid, abc):
            self.product_id = pid
            self.abc = abc

    schedule = build_schedule([Row("sku9", "B")], working_days=250)

    assert len(schedule) == 4
    assert all(t.product_id == "sku9" and t.abc == "B" for t in schedule)
