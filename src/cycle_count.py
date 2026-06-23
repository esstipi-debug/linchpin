"""Cycle-count planning (plan §2.4).

Cycle counting replaces the annual wall-to-wall count: high-value (A) SKUs are counted
often, low-value (C) rarely, and each SKU's counts are spread evenly across the working
year to keep the daily counting load balanced. Pure (no deps); consumes anything that
exposes ``.product_id`` and ``.abc`` (e.g. ``classification.SkuClassification``), so it
composes directly with the ABC engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CountPolicy:
    """Counts per year by ABC class."""

    counts_per_year: dict[str, int]


# A monthly, B quarterly, C annually - the common cycle-count cadence.
DEFAULT_POLICY = CountPolicy({"A": 12, "B": 4, "C": 1})


@dataclass(frozen=True)
class CountItem:
    product_id: str
    abc: str


@dataclass(frozen=True)
class CountTask:
    day: int            # 0-based working day in the year
    product_id: str
    abc: str


def count_frequency(policy: CountPolicy, abc: str) -> int:
    """Counts per year for an ABC class (0 for a class the policy does not cover)."""
    return policy.counts_per_year.get(abc, 0)


def annual_workload(items: Iterable, policy: CountPolicy = DEFAULT_POLICY) -> dict[str, int]:
    """Total counts per year, broken down by class plus a ``total``."""
    out: dict[str, int] = {}
    for item in items:
        freq = count_frequency(policy, item.abc)
        out[item.abc] = out.get(item.abc, 0) + freq
    out["total"] = sum(out.values())
    return out


def build_schedule(
    items: Iterable,
    policy: CountPolicy = DEFAULT_POLICY,
    *,
    working_days: int = 250,
) -> list[CountTask]:
    """Spread each SKU's required counts evenly across the working year, day-sorted."""
    if working_days <= 0:
        raise ValueError("working_days must be positive")

    tasks: list[CountTask] = []
    for item in items:
        freq = count_frequency(policy, item.abc)
        for k in range(freq):
            day = (k * working_days) // freq
            tasks.append(CountTask(day, item.product_id, item.abc))

    tasks.sort(key=lambda t: (t.day, t.product_id))
    return tasks


def daily_load(schedule: list[CountTask], working_days: int) -> list[int]:
    """Number of counts scheduled on each working day (index 0..working_days-1)."""
    load = [0] * working_days
    for task in schedule:
        load[task.day] += 1
    return load
