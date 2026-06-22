"""Tests for DDMRP buffer sizing and net-flow planning (capability M5).

DDMRP v3 (Ptak & Smith): red/yellow/green zones, the net-flow equation, and the
planning priority. Worked numbers: ADU=10/day, DLT=10d, LTF=0.5, VF=0.5.
  Yellow = ADU*DLT = 100
  Red    = ADU*DLT*LTF*(1+VF) = 50*1.5 = 75
  Green  = max(ADU*DLT*LTF, MOQ, ADU*order_cycle) = 50
  TOR=75, TOY=175, TOG=225
"""

import pytest

from src.ddmrp import (
    BufferZones,
    average_daily_usage,
    net_flow_position,
    planning_signal,
    size_buffer,
)


def _zones():
    return size_buffer(adu=10.0, dlt=10.0, ltf=0.5, vf=0.5)


def test_average_daily_usage():
    assert average_daily_usage([10, 10, 10, 10]) == pytest.approx(10.0)


def test_yellow_zone_is_adu_times_dlt():
    assert _zones().yellow == pytest.approx(100.0)


def test_red_zone_is_base_plus_safety():
    assert _zones().red == pytest.approx(75.0)


def test_green_zone_uses_max_rule_with_moq():
    z = size_buffer(adu=10.0, dlt=10.0, ltf=0.5, vf=0.5, moq=200.0)
    assert z.green == pytest.approx(200.0)  # MOQ dominates


def test_zone_tops():
    z = _zones()
    assert z.tor == pytest.approx(75.0)
    assert z.toy == pytest.approx(175.0)
    assert z.tog == pytest.approx(225.0)
    assert isinstance(z, BufferZones)


def test_net_flow_position():
    assert net_flow_position(on_hand=60, on_order=20, qualified_demand=30) == pytest.approx(50.0)


def test_red_triggers_urgent_reorder_to_top_of_green():
    sig = planning_signal(_zones(), on_hand=60, on_order=20, qualified_demand=30)  # NFP=50
    assert sig.zone == "red"
    assert sig.order_recommended
    assert sig.order_qty == pytest.approx(175.0)  # TOG - NFP = 225 - 50


def test_yellow_triggers_reorder():
    sig = planning_signal(_zones(), on_hand=120, on_order=0, qualified_demand=0)  # NFP=120
    assert sig.zone == "yellow"
    assert sig.order_recommended
    assert sig.order_qty == pytest.approx(105.0)  # 225 - 120


def test_green_does_not_reorder():
    sig = planning_signal(_zones(), on_hand=200, on_order=0, qualified_demand=0)  # NFP=200
    assert sig.zone == "green"
    assert not sig.order_recommended
    assert sig.order_qty == pytest.approx(0.0)


def test_over_green_does_not_reorder():
    sig = planning_signal(_zones(), on_hand=240, on_order=0, qualified_demand=0)  # NFP=240
    assert sig.zone == "over_green"
    assert not sig.order_recommended


def test_priority_lower_is_more_urgent():
    red = planning_signal(_zones(), on_hand=50, on_order=0, qualified_demand=0)
    green = planning_signal(_zones(), on_hand=200, on_order=0, qualified_demand=0)
    assert red.priority < green.priority
