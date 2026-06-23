"""DDMRP decoupled lead time over a BOM (plan §2.3).

A *decoupling point* is a strategically stocked buffer. Because the part is available
from stock, it resets the lead time seen by its parents. The **Decoupled (ASR) Lead
Time** of an item is therefore the longest cumulative lead-time path running through its
*unbuffered* components only - a buffered component contributes nothing to its parent's
path (it is pulled from stock), though its own buffer still takes its own decoupled lead
time to replenish.

Pure (no deps); complements ``ddmrp.py`` (buffer sizing / net-flow planning) with the
BOM-topology piece that tells you *where* buffering shortens the response time most.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BomItem:
    item_id: str
    lead_time: float
    children: tuple[str, ...] = ()   # component item_ids
    decoupled: bool = False          # True = a stocked buffer (decoupling point)


def _longest(
    bom: dict[str, BomItem],
    item_id: str,
    *,
    respect_buffers: bool,
    memo: dict[str, tuple[float, list[str]]],
    stack: set[str],
) -> tuple[float, list[str]]:
    """Return (lead time, critical path) of the longest qualifying path below item_id."""
    if item_id in stack:
        raise ValueError(f"BOM cycle detected at {item_id!r}")
    if item_id in memo:
        return memo[item_id]

    item = bom[item_id]  # KeyError if a referenced item is missing
    stack.add(item_id)

    best_val, best_path = 0.0, []
    for child_id in item.children:
        child = bom[child_id]  # validate the child exists
        if respect_buffers and child.decoupled:
            continue  # pulled from stock: contributes nothing to this path
        val, path = _longest(
            bom, child_id, respect_buffers=respect_buffers, memo=memo, stack=stack
        )
        if val > best_val:
            best_val, best_path = val, path

    stack.discard(item_id)
    result = (item.lead_time + best_val, [item_id, *best_path])
    memo[item_id] = result
    return result


def cumulative_lead_time(bom: dict[str, BomItem], item_id: str) -> float:
    """Classic cumulative lead time: the longest path ignoring any buffers."""
    return _longest(bom, item_id, respect_buffers=False, memo={}, stack=set())[0]


def decoupled_lead_time(bom: dict[str, BomItem], item_id: str) -> float:
    """Decoupled (ASR) lead time: longest path through unbuffered components only."""
    return _longest(bom, item_id, respect_buffers=True, memo={}, stack=set())[0]


def decoupling_path(bom: dict[str, BomItem], item_id: str) -> list[str]:
    """The unprotected critical path that sets the decoupled lead time, top-down."""
    return _longest(bom, item_id, respect_buffers=True, memo={}, stack=set())[1]


def all_decoupled_lead_times(bom: dict[str, BomItem]) -> dict[str, float]:
    """Decoupled lead time for every item in the BOM."""
    return {item_id: decoupled_lead_time(bom, item_id) for item_id in bom}
