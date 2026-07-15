"""Unit tests for jobs/scheduled_jobs.py -- the production JobRegistry wiring
consumed by webapp/app.py's POST /api/jobs/run-scheduled (F0 scheduler-into-
production wiring, see that module's own docstring for the full rationale).

Guarantees under test:
- production_registry() is a REAL, populated JobRegistry -- both
  price_monitor_cycle and price_watch_cycle are registered, not an empty
  registry (unlike jobs.scheduler.default_registry(), which ships empty on
  purpose);
- the registered ScheduledJob objects are the EXACT PRICE_MONITOR_JOB /
  PRICE_WATCH_JOB singletons jobs/price_monitor.py and jobs/price_watch.py
  already define and test via run_once() elsewhere -- never a second,
  re-implemented copy;
- production_registry() is a lazily constructed, cached singleton (same
  convention as jobs.scheduler.default_registry());
- PRODUCTION_JOB_IDS is derived from those same two ScheduledJob objects'
  own .id, never a hand-copied string literal that could drift.
"""
from __future__ import annotations

import jobs.scheduled_jobs as scheduled_jobs_module
from jobs.price_monitor import PRICE_MONITOR_JOB
from jobs.price_watch import PRICE_WATCH_JOB
from jobs.scheduled_jobs import PRODUCTION_JOB_IDS, production_registry
from jobs.scheduler import JobRegistry


def test_production_job_ids_match_the_real_scheduled_jobs():
    assert PRODUCTION_JOB_IDS == (PRICE_MONITOR_JOB.id, PRICE_WATCH_JOB.id)
    assert PRODUCTION_JOB_IDS == ("price_monitor_cycle", "price_watch_cycle")


def test_production_registry_is_a_real_populated_registry(monkeypatch):
    monkeypatch.setattr(scheduled_jobs_module, "_production_registry", None)

    registry = production_registry()

    assert isinstance(registry, JobRegistry)
    assert {job.id for job in registry.list()} == set(PRODUCTION_JOB_IDS)


def test_production_registry_registers_the_exact_same_job_objects(monkeypatch):
    """Not a re-implemented copy -- the SAME PRICE_MONITOR_JOB/PRICE_WATCH_JOB
    singletons jobs/price_monitor.py and jobs/price_watch.py already ship and
    test via their own run_once() coverage."""
    monkeypatch.setattr(scheduled_jobs_module, "_production_registry", None)

    registry = production_registry()

    assert registry.get("price_monitor_cycle") is PRICE_MONITOR_JOB
    assert registry.get("price_watch_cycle") is PRICE_WATCH_JOB


def test_production_registry_is_a_lazily_constructed_singleton(monkeypatch):
    monkeypatch.setattr(scheduled_jobs_module, "_production_registry", None)

    first = production_registry()
    second = production_registry()

    assert first is second
