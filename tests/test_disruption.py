"""Unit tests for the GDELT disruption engine (src/disruption.py).

Every test injects a fetcher or works on canned bodies -- nothing here touches
the network. Fixtures live in tests/fixtures/gdelt/.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src import disruption as D
from src.risk import RiskFactor, assess_portfolio

FIXTURES = Path(__file__).parent / "fixtures" / "gdelt"
_ACME = (FIXTURES / "acme_electronics.json").read_text(encoding="utf-8")
_EMPTY = (FIXTURES / "empty.json").read_text(encoding="utf-8")
_RATELIMIT = (FIXTURES / "ratelimited.txt").read_text(encoding="utf-8")
# The most recent article in the Acme fixture is 20260722; freeze "now" just after.
_NOW = datetime(2026, 7, 24, tzinfo=timezone.utc)


def _fixed_fetcher(body: str) -> D.Fetcher:
    return lambda url: body


# -- country FIPS mapping ---------------------------------------------------

def test_country_to_fips_handles_the_iso_gotchas():
    # Australia is AS (not AU) and Chile is CI (not CL) in FIPS 10-4.
    assert D.country_to_fips("Australia") == "AS"
    assert D.country_to_fips("Chile") == "CI"
    assert D.country_to_fips("Brazil") == "BR"
    assert D.country_to_fips("United Kingdom") == "UK"


def test_country_to_fips_accepts_a_known_code_and_rejects_junk():
    assert D.country_to_fips("BR") == "BR"
    assert D.country_to_fips("") is None
    assert D.country_to_fips(None) is None
    assert D.country_to_fips("Nowhereistan") is None


# -- query / url building ---------------------------------------------------

def test_build_query_anchors_name_and_ors_themes():
    q = D.build_query("Acme Electronics", themes=("STRIKE", "NATURAL_DISASTER_FLOOD"))
    assert '"Acme Electronics"' in q
    assert "theme:STRIKE OR theme:NATURAL_DISASTER_FLOOD" in q
    # no country filter unless asked
    assert "sourcecountry" not in q


def test_build_query_adds_country_filter_when_given():
    q = D.build_query("Pacific Freight", country="Australia", themes=("STRIKE",))
    assert "sourcecountry:AS" in q


def test_build_query_strips_embedded_quotes():
    q = D.build_query('Ac"me', themes=("STRIKE",))
    assert '"Acme"' in q


def test_build_url_is_artlist_json_datedesc_and_caps_records():
    url = D.build_url("q", timespan="3m", maxrecords=9999)
    assert url.startswith(D.GDELT_ENDPOINT + "?")
    assert "mode=ArtList" in url
    assert "format=json" in url
    assert "sort=DateDesc" in url
    assert "maxrecords=250" in url  # capped at the GDELT max


# -- response parsing (the GDELT quirks) ------------------------------------

def test_parse_articles_reads_metadata_and_infers_category():
    arts = D.parse_articles(_ACME)
    assert len(arts) == 5
    first = arts[0]
    assert first.domain == "example-news.com.br"
    assert first.language == "Portuguese"
    assert first.seendate == datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
    # "Greve no Porto de Santos" -> port/greve -> logistics/operational keyword hit
    assert first.category in {"logistics", "operational"}


def test_parse_articles_empty_result_is_bare_braces_not_articles_key():
    # GDELT returns literally {} for no results -> must not KeyError.
    assert D.parse_articles(_EMPTY) == []


def test_parse_articles_detects_plaintext_rate_limit_notice():
    with pytest.raises(D.GdeltRateLimited):
        D.parse_articles(_RATELIMIT)


def test_parse_articles_raises_on_unparseable_json():
    with pytest.raises(D.GdeltUnavailable):
        D.parse_articles('{"articles": [ this is not json ')


def test_parse_articles_skips_rows_with_bad_dates():
    body = '{"articles":[{"url":"u","title":"t","seendate":"not-a-date","domain":"d","language":"English","sourcecountry":"US"}]}'
    assert D.parse_articles(body) == []


def test_parse_articles_tolerates_null_articles_and_non_dict_rows():
    # valid JSON but articles is null / holds junk -> degrade, don't crash
    assert D.parse_articles('{"articles": null}') == []
    assert D.parse_articles('{}') == []
    ok = D.parse_articles(
        '{"articles":[null,"junk",{"url":"u","title":"Flood hits plant","seendate":"20260722T093000Z",'
        '"domain":"d","language":"English","sourcecountry":"US"}]}'
    )
    assert len(ok) == 1
    assert ok[0].domain == "d"


def test_parse_articles_raises_when_articles_is_wrong_type():
    with pytest.raises(D.GdeltUnavailable):
        D.parse_articles('{"articles": {"not": "a list"}}')


def test_parse_articles_handles_a_bom_prefixed_body():
    # a leading BOM must not be mistaken for the plaintext rate-limit notice
    assert D.parse_articles("﻿" + _EMPTY) == []
    assert len(D.parse_articles("﻿" + _ACME)) == 5


def test_infer_category_is_not_fooled_by_port_inside_report_or_support():
    # the false-friend that mislabeled bankruptcy/strike headlines as logistics
    assert D._infer_category("Report: Acme files for bankruptcy") == "financial"
    assert D._infer_category("Support grows for striking workers") == "operational"
    # a genuine port headline still resolves to logistics
    assert D._infer_category("Port congestion delays container shipments") == "logistics"


# -- exposure scoring -------------------------------------------------------

def test_exposure_score_is_zero_with_no_articles():
    assert D._exposure_score(0, 0.0) == 0.0


def test_exposure_score_rises_with_volume_and_saturates():
    s1 = D._exposure_score(1, 0.0)
    s5 = D._exposure_score(5, 0.0)
    s50 = D._exposure_score(50, 0.0)
    assert 0 < s1 < s5 < s50 <= 1.0
    # saturating: going 5 -> 50 adds less than 0 -> 5
    assert (s50 - s5) < (s5 - 0.0)


def test_exposure_score_decays_with_staleness():
    fresh = D._exposure_score(10, 2.0)
    stale = D._exposure_score(10, 120.0)
    assert fresh > stale > 0


# -- score_supplier ---------------------------------------------------------

def test_score_supplier_aggregates_signal():
    arts = D.parse_articles(_ACME)
    sig = D.score_supplier("Acme Electronics", "Brazil", 4_200_000, arts, now=_NOW)
    assert sig.article_count == 5
    assert sig.distinct_sources == 5
    assert sig.recency_days == pytest.approx(2.0 - 9.5 / 24, abs=0.6)  # ~2 days
    assert 0 < sig.exposure_score <= 1.0
    assert sig.most_recent == datetime(2026, 7, 22, 9, 30, tzinfo=timezone.utc)
    assert len(sig.sample_articles) == 3
    assert sum(sig.categories.values()) == 5


def test_score_supplier_with_no_articles_is_inert():
    sig = D.score_supplier("Quiet Co", "New Zealand", 0.0, [], now=_NOW)
    assert sig.article_count == 0
    assert sig.exposure_score == 0.0
    assert sig.most_recent is None
    assert sig.recency_days == float("inf")
    assert sig.dominant_category == "supply"


# -- the wiring: to_risk_factor + assess_portfolio --------------------------

def test_to_risk_factor_maps_signal_into_the_risk_engine():
    arts = D.parse_articles(_ACME)
    sig = D.score_supplier("Acme Electronics", "Brazil", 4_200_000, arts, now=_NOW)
    rf = D.to_risk_factor(sig)
    assert isinstance(rf, RiskFactor)
    assert rf.name == "Disruption exposure: Acme Electronics"
    assert rf.likelihood == sig.exposure_score          # screen -> likelihood
    assert rf.impact_value == 4_200_000                 # spend -> impact
    assert rf.owner == "Acme Electronics"
    # feeds the existing engine unchanged
    report = assess_portfolio([rf])
    assert report.assessments[0].name == "Disruption exposure: Acme Electronics"
    assert report.total_emv > 0


def test_to_risk_factor_falls_back_to_nominal_impact_without_spend():
    sig = D.score_supplier("No Spend Co", "US", 0.0,
                           D.parse_articles(_ACME), now=_NOW)
    rf = D.to_risk_factor(sig)
    assert rf.impact_value == D._DEFAULT_IMPACT_VALUE


# -- scan_suppliers with the injected fetcher -------------------------------

def test_scan_suppliers_uses_injected_fetcher_and_ranks_by_signal():
    rows = [
        D.SupplierRow("Acme Electronics", "Brazil", 4_200_000),
        D.SupplierRow("Calm Supplier", "New Zealand", 500_000),
    ]

    def fetcher(url: str) -> str:
        return _ACME if "Acme" in url else _EMPTY

    sigs = D.scan_suppliers(rows, fetcher=fetcher, now=_NOW)
    by_name = {s.supplier: s for s in sigs}
    assert by_name["Acme Electronics"].article_count == 5
    assert by_name["Calm Supplier"].article_count == 0
    assert by_name["Acme Electronics"].exposure_score > by_name["Calm Supplier"].exposure_score


def test_scan_suppliers_degrades_a_failing_fetch_to_a_flagged_zero_row():
    def broken(url: str) -> str:
        raise D.GdeltUnavailable("network down")

    sigs = D.scan_suppliers([D.SupplierRow("Acme", "US", 1000)], fetcher=broken, now=_NOW)
    assert len(sigs) == 1
    assert sigs[0].fetch_failed is True
    assert sigs[0].article_count == 0
    assert sigs[0].exposure_score == 0.0


def test_scan_suppliers_survives_a_rate_limit_on_one_supplier():
    calls = {"n": 0}

    def flaky(url: str) -> str:
        calls["n"] += 1
        return _RATELIMIT if calls["n"] == 1 else _ACME

    rows = [D.SupplierRow("First", "US"), D.SupplierRow("Second", "US")]
    sigs = D.scan_suppliers(rows, fetcher=flaky, now=_NOW)
    assert sigs[0].fetch_failed is True
    assert sigs[1].fetch_failed is False
    assert sigs[1].article_count == 5


def test_module_never_imports_writeback():
    # Read-only invariant: the disruption screen must never import the writeback
    # surface. Check for an actual import statement (the module docstring mentions
    # writeback by name to promise exactly this, so a bare substring check lies).
    import ast

    tree = ast.parse((Path(__file__).parents[1] / "src" / "disruption.py").read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any("writeback" in m for m in imported)
