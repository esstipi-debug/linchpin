"""Tests for scm_agent/merchant_alerts.py -- the Kern Alerts merchant-facing
render layer. Pure-function tests: build Events by hand, assert the rendered
MerchantAlert, no state/store/network."""

from __future__ import annotations

from scm_agent.events import Event
from scm_agent.merchant_alerts import (
    ALERTS_V1_EVENT_TYPES,
    DISCLAIMER,
    render_merchant_alert,
)


def _stock_event(event_type: str, sku: str, severity: str, *, on_hand=None, reorder_point=None, message="msg") -> Event:
    rows = []
    if on_hand is not None and reorder_point is not None:
        rows = [{"product_id": sku, "on_hand": on_hand, "reorder_point": reorder_point, "avg_daily_demand": 1.0}]
    return Event(
        type=event_type,
        severity=severity,
        source="monitors",
        dedup_key=f"{sku}:{event_type}",
        sku=sku,
        payload={"message": message, "rows": rows},
    )


def test_empty_events_still_renders_with_disclaimer():
    alert = render_merchant_alert([], merchant_name="Tienda X")
    assert alert.is_empty
    assert alert.alert_count == 0
    assert alert.high_severity_count == 0
    assert DISCLAIMER in alert.body
    assert "Tienda X" in alert.subject
    assert "sin alertas" in alert.subject.lower()


def test_disclaimer_present_on_every_non_empty_send():
    events = [_stock_event("rop_breach", "SKU-1", "medium", on_hand=15, reorder_point=20)]
    alert = render_merchant_alert(events, merchant_name="Tienda X")
    assert not alert.is_empty
    assert alert.body.rstrip().endswith(DISCLAIMER)


def test_rop_breach_suggests_floor_to_reorder_point_quantity():
    # gap = reorder_point - on_hand = 20 - 15 = 5
    events = [_stock_event("rop_breach", "SKU-1", "medium", on_hand=15, reorder_point=20)]
    alert = render_merchant_alert(events, merchant_name="M")
    assert alert.lines[0].suggested_order_qty == 5
    assert "~5" in alert.body


def test_suggested_qty_rounds_up_a_fractional_gap():
    events = [_stock_event("stockout_projected", "SKU-1", "high", on_hand=10.4, reorder_point=20)]
    alert = render_merchant_alert(events, merchant_name="M")
    # gap = 9.6 -> ceil -> 10
    assert alert.lines[0].suggested_order_qty == 10


def test_excess_growing_never_suggests_a_buy_quantity():
    events = [_stock_event("excess_growing", "SKU-9", "low", message="SKU-9: excess growing")]
    alert = render_merchant_alert(events, merchant_name="M")
    assert alert.alert_count == 1
    assert alert.lines[0].suggested_order_qty is None
    assert "Sugerido pedir" not in alert.body


def test_missing_row_fields_yield_no_fabricated_quantity():
    events = [_stock_event("rop_breach", "SKU-1", "medium")]  # no rows
    alert = render_merchant_alert(events, merchant_name="M")
    assert alert.lines[0].suggested_order_qty is None


def test_non_v1_event_types_are_ignored():
    events = [
        _stock_event("rop_breach", "SKU-1", "medium", on_hand=15, reorder_point=20),
        Event(type="competitor_price_move", severity="high", source="monitors",
              dedup_key="x", sku="SKU-2", payload={"message": "price move"}),
        Event(type="forecast_error_out_of_band", severity="high", source="monitors",
              dedup_key="y", sku="SKU-3", payload={"message": "forecast off"}),
    ]
    alert = render_merchant_alert(events, merchant_name="M")
    assert alert.alert_count == 1
    assert alert.lines[0].sku == "SKU-1"
    assert "competitor_price_move" not in ALERTS_V1_EVENT_TYPES


def test_alerts_sorted_most_urgent_first():
    events = [
        _stock_event("excess_growing", "SKU-C", "low", message="c"),
        _stock_event("stockout_projected", "SKU-A", "high", on_hand=2, reorder_point=20),
        _stock_event("rop_breach", "SKU-B", "medium", on_hand=15, reorder_point=20),
    ]
    alert = render_merchant_alert(events, merchant_name="M")
    severities = [line.severity for line in alert.lines]
    assert severities == ["high", "medium", "low"]
    assert alert.high_severity_count == 1


def test_subject_counts_urgent_alerts():
    events = [
        _stock_event("stockout_projected", "SKU-A", "high", on_hand=2, reorder_point=20),
        _stock_event("stockout_projected", "SKU-B", "high", on_hand=1, reorder_point=20),
    ]
    alert = render_merchant_alert(events, merchant_name="M")
    assert "2 urgentes" in alert.subject


def test_render_is_pure_does_not_mutate_input_list():
    events = [
        _stock_event("excess_growing", "SKU-C", "low", message="c"),
        _stock_event("stockout_projected", "SKU-A", "high", on_hand=2, reorder_point=20),
    ]
    original_order = [e.sku for e in events]
    render_merchant_alert(events, merchant_name="M")
    assert [e.sku for e in events] == original_order
