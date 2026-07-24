"""Tests for jobs/monitors_job.py -- the Control Tower "sense" cycle wrapped as
a registrable ScheduledJob. Golden-rule-9 batch path: direct calls with an
injected in-memory ledger + isolated tmp store, no scheduler loop, no network."""

from __future__ import annotations

import pandas as pd

from jobs.monitors_job import (
    MONITORS_CADENCE_MINUTES,
    MONITORS_JOB,
    run_concierge_alerts,
    run_monitors_cycle,
)
from scm_agent.events import EventLedger
from scm_agent.merchant_alerts import DISCLAIMER
from src.state.store import StateStore
from src.state.system_state import snapshot


def _store(tmp_path) -> StateStore:
    return StateStore(tmp_path / "state")


def _stock(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_job_shape_matches_scheduledjob_contract():
    assert MONITORS_JOB.id == "control_tower_monitors"
    assert MONITORS_JOB.func is run_monitors_cycle
    assert MONITORS_JOB.trigger == "interval"
    assert MONITORS_JOB.trigger_args == {"minutes": MONITORS_CADENCE_MINUTES}


def test_empty_state_yields_zero_events_and_never_raises(tmp_path):
    report = run_monitors_cycle(
        ledger=EventLedger(":memory:"), store=_store(tmp_path), notify_operator=False
    )
    assert report.event_count == 0
    assert report.notified_operator is False


def test_cycle_records_events_and_tallies_by_severity_and_type(tmp_path):
    store = _store(tmp_path)
    # at/below reorder point with <7d cover -> stockout_projected (high).
    snapshot(
        "stock",
        _stock([{"product_id": "SKU-1", "on_hand": 10.0, "reorder_point": 20.0, "avg_daily_demand": 5.0}]),
        "1",
        store=store,
    )
    report = run_monitors_cycle(ledger=EventLedger(":memory:"), store=store, notify_operator=False)

    assert report.event_count >= 1
    assert report.by_severity.get("high", 0) >= 1
    assert "stockout_projected" in report.by_type


def test_notify_off_by_default_via_env(tmp_path, monkeypatch):
    monkeypatch.delenv("LINCHPIN_MONITORS_NOTIFY", raising=False)
    report = run_monitors_cycle(ledger=EventLedger(":memory:"), store=_store(tmp_path))
    assert report.notified_operator is False


def test_notify_on_via_env_calls_notify_when_events_exist(tmp_path, monkeypatch):
    store = _store(tmp_path)
    snapshot(
        "stock",
        _stock([{"product_id": "SKU-1", "on_hand": 10.0, "reorder_point": 20.0, "avg_daily_demand": 5.0}]),
        "1",
        store=store,
    )
    calls: dict[str, str] = {}

    def fake_notify(message, **kwargs):
        calls["message"] = message
        return True

    monkeypatch.setenv("LINCHPIN_MONITORS_NOTIFY", "1")
    monkeypatch.setattr("jobs.monitors_job.notify", fake_notify)
    report = run_monitors_cycle(ledger=EventLedger(":memory:"), store=store)

    assert report.notified_operator is True
    assert "Control Tower" in calls["message"]


def test_notify_enabled_but_no_events_does_not_notify(tmp_path, monkeypatch):
    def fake_notify(message, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("notify called with no events")

    monkeypatch.setattr("jobs.monitors_job.notify", fake_notify)
    report = run_monitors_cycle(
        ledger=EventLedger(":memory:"), store=_store(tmp_path), notify_operator=True
    )
    assert report.event_count == 0
    assert report.notified_operator is False


# -- concierge runner (Kern Alerts Fase 1) -------------------------------------


def test_concierge_run_over_empty_state_is_a_clean_no_alert_digest(tmp_path):
    alert = run_concierge_alerts(merchant_name="Tienda X", store=_store(tmp_path))
    assert alert.is_empty
    assert DISCLAIMER in alert.body


def test_concierge_run_renders_a_merchant_ready_alert(tmp_path):
    store = _store(tmp_path)
    snapshot(
        "stock",
        _stock([{"product_id": "SKU-1", "on_hand": 10.0, "reorder_point": 20.0, "avg_daily_demand": 5.0}]),
        "1",
        store=store,
    )
    alert = run_concierge_alerts(merchant_name="Tienda X", store=store)

    assert alert.alert_count == 1
    assert alert.high_severity_count == 1  # stockout_projected == high
    assert "Tienda X" in alert.subject
    assert alert.body.rstrip().endswith(DISCLAIMER)
    # floor-to-reorder-point suggested qty surfaced (20 - 10 = 10)
    assert alert.lines[0].suggested_order_qty == 10
