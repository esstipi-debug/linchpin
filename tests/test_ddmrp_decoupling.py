"""Tests for DDMRP decoupled lead time over a BOM (plan §2.3).

A decoupling point is a stocked buffer; it resets downstream lead time because the part
is available from stock. The Decoupled (ASR) Lead Time of an item is the longest
cumulative lead-time path of *unbuffered* components beneath it. Pure - no deps.
"""

import pytest

from src.ddmrp_decoupling import (
    BomItem,
    all_decoupled_lead_times,
    cumulative_lead_time,
    decoupled_lead_time,
    decoupling_path,
)


def _bom(buffer=()):
    decoupled = set(buffer)
    spec = {
        "FG": (2.0, ("SubA", "SubB")),
        "SubA": (5.0, ("Raw1",)),
        "SubB": (3.0, ("Raw2",)),
        "Raw1": (10.0, ()),
        "Raw2": (4.0, ()),
    }
    return {
        i: BomItem(i, lt, children, decoupled=(i in decoupled))
        for i, (lt, children) in spec.items()
    }


def test_cumulative_lead_time_is_the_longest_path():
    bom = _bom()
    # FG(2) + SubA(5) + Raw1(10) = 17 (longer than the SubB/Raw2 = 7 branch)
    assert cumulative_lead_time(bom, "FG") == 17.0
    assert cumulative_lead_time(bom, "SubB") == 7.0


def test_decoupled_lt_equals_cumulative_when_nothing_buffered():
    bom = _bom()
    assert decoupled_lead_time(bom, "FG") == 17.0


def test_buffering_the_long_branch_cuts_the_decoupled_lt():
    bom = _bom(buffer=("SubA",))
    # SubA available from stock -> FG(2) + SubB(3) + Raw2(4) = 9
    assert decoupled_lead_time(bom, "FG") == 9.0


def test_buffered_items_own_dlt_ignores_its_own_buffer_flag():
    bom = _bom(buffer=("SubA",))
    # SubA's own buffer still takes SubA(5) + Raw1(10) = 15 to replenish
    assert decoupled_lead_time(bom, "SubA") == 15.0


def test_leaf_item_dlt_is_its_own_lead_time():
    assert decoupled_lead_time(_bom(), "Raw1") == 10.0


def test_decoupling_path_is_the_unprotected_critical_path():
    assert decoupling_path(_bom(), "FG") == ["FG", "SubA", "Raw1"]
    assert decoupling_path(_bom(buffer=("SubA",)), "FG") == ["FG", "SubB", "Raw2"]


def test_all_decoupled_lead_times_covers_every_item():
    dlts = all_decoupled_lead_times(_bom(buffer=("SubA",)))
    assert dlts["FG"] == 9.0
    assert dlts["Raw1"] == 10.0
    assert set(dlts) == {"FG", "SubA", "SubB", "Raw1", "Raw2"}


def test_shared_component_is_memoized():
    # diamond BOM: 'Shared' is reached via both L and R.
    bom = {
        "Top": BomItem("Top", 1.0, ("L", "R")),
        "L": BomItem("L", 2.0, ("Shared",)),
        "R": BomItem("R", 3.0, ("Shared",)),
        "Shared": BomItem("Shared", 5.0, ()),
    }
    # Top(1) + R(3) + Shared(5) = 9 is the longest; Shared is memoized after L visits it.
    assert decoupled_lead_time(bom, "Top") == 9.0
    assert decoupling_path(bom, "Top") == ["Top", "R", "Shared"]


def test_missing_child_raises():
    bom = {"FG": BomItem("FG", 1.0, ("Ghost",))}
    with pytest.raises(KeyError):
        decoupled_lead_time(bom, "FG")


def test_cycle_raises():
    bom = {
        "A": BomItem("A", 1.0, ("B",)),
        "B": BomItem("B", 1.0, ("A",)),
    }
    with pytest.raises(ValueError):
        decoupled_lead_time(bom, "A")
