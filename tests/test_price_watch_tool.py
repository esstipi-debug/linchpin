"""Tests for Task 11 / PR-11: exposing the discovery-assisted price-watch
playbook (``jobs/price_watch.py``, Tasks 3/5/6/9) as a routable agent tool --
``scm_agent.tools.price_watch_tool()`` + ``scm_agent.tool_options.
price_watch_options`` + ``jobs.qa.verify_price_watch`` + ``jobs.
price_watch_deliverable.write_operational``.

This PR adds NO new business logic (no new match/acquisition/escalation
decision) -- it only wires already-tested machinery behind the ``Tool``
interface. The one genuinely new, safety-critical piece of logic is the
``options`` hook's R5 handling: a pending ceiling-raise escalation
(``PriceWatchCycleReport.pending_escalations``, Task 9) must NEVER be
flattened into the happy-path ranked options or reported as ``EXECUTED`` --
see ``test_options_surfaces_pending_ceiling_raise`` below, the highest-stakes
test in this file.

NOTE on the "39th tool" framing in the original task brief: by the time this
PR landed, ``digital_twin_tool`` (a parallel, unrelated plan) had already been
merged as the 33rd registered tool, and ``price_intelligence_tool`` (an
earlier PR in THIS plan) as the 39th -- so ``price_watch_tool`` is actually
the 40th. ``test_registry_now_has_40_tools`` asserts the real, current count,
not the brief's stale arithmetic.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from jobs import price_watch_deliverable, qa
from jobs.price_monitor import PairOutcome
from jobs.price_watch import PriceWatchCycleReport
from scm_agent import intent, llm, tool_options, tools
from scm_agent.orchestrator import Orchestrator
from src.guided import EXECUTED, HANDOFF, OPTIONS, as_executed, passed_guided
from src.pricing_intel.models import SiteConfig
from src.pricing_intel.watch_policy import NEEDS_CEILING_RAISE, plan_watch_escalation

REPO_ROOT = Path(__file__).resolve().parent.parent

NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
SITE = "discovered-retailer.test"
REF = "https://discovered-retailer.test/p/1"
PID = "SKU-100"


# -- fixtures -------------------------------------------------------------


def _outcome(
    status: str = "accepted", reason: str = "ok", *, site: str = SITE, ref: str = REF, pid: str = PID,
) -> PairOutcome:
    return PairOutcome(site=site, competitor_sku_ref=ref, matched_product_id=pid, status=status, reason=reason)


def _report(outcomes: list[PairOutcome], pending=()) -> PriceWatchCycleReport:
    return PriceWatchCycleReport(
        now=NOW, pairs_checked=len(outcomes), outcomes=tuple(outcomes), pending_escalations=tuple(pending),
    )


def _site_config(max_tier: str = "L1") -> SiteConfig:
    return SiteConfig(
        domain=SITE, robots_txt_respected=True, robots_checked_at="2026-07-01",
        tos_summary="auto-approved, robots.txt only", tos_decision="limited",
        rate_limit_seconds=5.0, max_tier_allowed=max_tier,
    )


def _pending_ceiling_raise():
    """A REAL needs_ceiling_raise GuidedOutcome, built through the actual R5
    guard (``watch_policy.plan_watch_escalation``, Task 9's own dependency) --
    not hand-faked, so the escalation-surfacing tests below prove the tool
    layer carries the genuine artifact through, not a look-alike stand-in."""
    decision = plan_watch_escalation(
        site_config=_site_config("L1"), current_cadence_hours=4.0, desired_cadence_hours=1.0,
        desired_tier="L2", sku_value_rank="A", now=NOW,
    )
    assert decision.kind == NEEDS_CEILING_RAISE  # sanity: this really is a ceiling-raise case
    return decision.guided


# -- registration + routing ------------------------------------------------


def test_tool_registered_and_routable():
    reg = tools.build_default_registry()
    tool = reg.get("price_watch")

    assert tool.key == "price_watch"
    assert tool.requires_data is False
    assert tool.options is tool_options.price_watch_options

    classified = intent.classify(
        "descubre productos de la competencia y homologa productos competencia, luego vigila los "
        "precios de la competencia",
        reg, llm.RulesFallback(),
    )
    assert classified.job_type == "price_watch"


def test_routes_on_english_discovery_phrasing_without_colliding_with_price_intelligence():
    reg = tools.build_default_registry()

    classified = intent.classify(
        "start a recurring competitor price watch: run a price watch cycle covering competitor "
        "price discovery for this new site",
        reg, llm.RulesFallback(),
    )
    assert classified.job_type == "price_watch"


def test_registry_now_has_40_tools():
    reg = tools.build_default_registry()
    assert len(reg.list()) == 40


def test_scm_agent_tools_module_imports_without_circular_import():
    """Proves the lazy-import recipe: a FRESH process importing scm_agent.tools
    (which registers price_watch_tool()) and building the registry must succeed --
    a top-of-module `from jobs import price_watch`/`price_priority` would recreate
    the circular-import hazard price_intelligence_tool() already documents (both
    modules import scm_agent.* transitively). Run in a subprocess, not in-process:
    within the same pytest session scm_agent is already cached in sys.modules, so
    an in-process import would hit the cache and never actually re-exercise the
    package's real init order."""
    result = subprocess.run(
        [sys.executable, "-c", "from scm_agent import tools; tools.build_default_registry(); print('ok')"],
        cwd=str(REPO_ROOT), env={**os.environ, "PYTHONPATH": "."},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


# -- options hook: happy path -----------------------------------------------


def test_options_hook_returns_protected_outcome():
    report = _report([_outcome(), _outcome(status="skipped", reason="tier_not_approved", ref=REF + "2")])

    outcome = tool_options.price_watch_options(report)

    assert passed_guided(outcome)
    assert outcome.status == OPTIONS
    assert len(outcome.options) >= 2
    assert sum(1 for o in outcome.options if o.recommended) == 1
    assert all(o.action for o in outcome.options)


def test_options_hook_ranks_flagged_investigation_first_when_present():
    report = _report([_outcome(status="quarantined", reason="delta_exceeded")])

    outcome = tool_options.price_watch_options(report)

    assert passed_guided(outcome)
    assert "flagged" in outcome.options[0].label.lower() or "flagged" in outcome.options[1].label.lower()


# -- options hook: R5 safety-critical --------------------------------------


def test_options_surfaces_pending_ceiling_raise():
    """THE highest-stakes test in this file: when the cycle produced a pending
    ceiling-raise request (Task 9's R5), the options hook must NEVER report
    EXECUTED and must NEVER silently flatten the escalation into the ordinary
    ranked-options list -- it must genuinely carry the escalation (the exact
    prepared HandoffPacket) so an operator actually sees it."""
    pending = _pending_ceiling_raise()
    report = _report([_outcome()], pending=[pending])

    outcome = tool_options.price_watch_options(report)

    assert passed_guided(outcome)
    assert outcome.status != EXECUTED
    assert outcome.status == HANDOFF
    # genuinely carries the escalation -- not dropped, not silently flattened.
    assert len(outcome.handoffs) == 1
    assert outcome.handoffs[0].title == pending.handoffs[0].title
    assert "ceiling" in outcome.handoffs[0].title.lower()
    assert outcome.handoffs[0].steps == pending.handoffs[0].steps
    assert outcome.residuals  # the human-owner residual travels too.
    # the routine ranked next steps are NOT lost either -- still visible at
    # the outcome's top level (mirrors src.escalation._maybe_escalate).
    assert len(outcome.options) >= 2


def test_options_handles_multiple_pending_escalations():
    p1 = _pending_ceiling_raise()
    p2 = _pending_ceiling_raise()
    report = _report([_outcome()], pending=[p1, p2])

    outcome = tool_options.price_watch_options(report)

    assert passed_guided(outcome)
    assert outcome.status == HANDOFF
    assert len(outcome.handoffs) == 2


# -- QA gate: structural + R5 safety net (checked again, not just options) --


def test_qa_passes_a_clean_cycle():
    report = _report([_outcome(), _outcome(status="skipped", reason="circuit_open", ref=REF + "2")])
    assert qa.verify_price_watch(report) == []


def test_qa_flags_pairs_checked_mismatch():
    report = _report([_outcome()])
    bad = replace(report, pairs_checked=5)

    issues = qa.verify_price_watch(bad)

    assert any("pairs_checked" in i for i in issues)


def test_qa_flags_invalid_outcome_status():
    report = _report([_outcome(status="bogus")])

    issues = qa.verify_price_watch(report)

    assert any("invalid status" in i for i in issues)


def test_qa_passes_a_genuine_pending_ceiling_raise():
    report = _report([_outcome()], pending=[_pending_ceiling_raise()])
    assert qa.verify_price_watch(report) == []


def test_qa_flags_a_pending_escalation_wrongly_reported_as_executed():
    """R5 defense in depth: even if a future bug made some caller hand the QA
    gate a pending_escalations entry with status EXECUTED, verify_price_watch
    must catch it independently of the options hook."""
    bad = as_executed("should never happen for a tier raise")
    report = _report([_outcome()], pending=[bad])

    issues = qa.verify_price_watch(report)

    assert any("EXECUTED" in i for i in issues)


# -- deliverable writer -------------------------------------------------------


def test_write_operational_writes_one_row_per_outcome(tmp_path):
    report = _report([_outcome(), _outcome(status="skipped", reason="tier_not_approved", ref=REF + "2")])

    written = price_watch_deliverable.write_operational(report, tmp_path, client="Acme")

    df = pd.read_csv(written["csv"])
    assert len(df) == 2
    assert set(df["status"]) == {"accepted", "skipped"}


def test_write_operational_writes_header_only_csv_when_no_outcomes(tmp_path):
    report = _report([])

    written = price_watch_deliverable.write_operational(report, tmp_path)

    df = pd.read_csv(written["csv"])
    assert len(df) == 0
    assert list(df.columns) == ["site", "competitor_sku_ref", "matched_product_id", "status", "reason"]


# -- prepare(): needs seed_url, gated crawl -----------------------------------


def test_prepare_needs_data_without_a_seed_url():
    from scm_agent.types import JobRequest

    reg = tools.build_default_registry()
    tool = reg.get("price_watch")

    prep = tool.prepare(JobRequest(brief="watch competitor prices"), llm.RulesFallback())

    assert prep.status == "needs_data"
    assert prep.messages


# -- end-to-end through the orchestrator (prepare -> run -> qa -> deliver) --


_PRODUCT_HTML = """<html><head><title>Widget</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Product","name":"Widget",
 "offers":{"@type":"Offer","price":"9.99","priceCurrency":"USD"}}
</script></head><body><h1>Widget</h1></body></html>"""


def test_runs_end_to_end_through_the_orchestrator(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from jobs import price_watch as pw

    domain = "shop.example.test"
    seed_url = f"https://{domain}/"
    df = pd.DataFrame([{"url": f"https://{domain}/p/1", "status": 200, "title": "Widget",
                         "page_html": _PRODUCT_HTML}])
    monkeypatch.setattr(pw, "_crawl_domain", lambda seed, **kwargs: df)

    orch = Orchestrator(registry=tools.build_default_registry(), provider=llm.RulesFallback())

    res = orch.run(
        "watch competitor prices via a price watch cycle: descubre productos de la competencia",
        client="Acme", out_dir=tmp_path,
        overrides={
            "seed_url": seed_url,
            "config_dir": tmp_path / "sites",
            "robots_reader": lambda robots_url, user_agent: True,
            "now": NOW,
        },
    )

    assert res.status == "ok", res.summary
    assert res.tool == "price_watch"
    assert res.guided is not None
    # no confirmed pairs exist yet (no our_catalog supplied) -> the happy-path
    # ranked options, never a dead end.
    assert res.guided.status == OPTIONS
    assert Path(res.deliverables["csv"]).exists()
    written_csv = pd.read_csv(res.deliverables["csv"])
    assert list(written_csv.columns) == ["site", "competitor_sku_ref", "matched_product_id", "status", "reason"]
