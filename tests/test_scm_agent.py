"""Tests for the scm_agent orchestrator package."""

import pytest

from scm_agent import llm, tools
from scm_agent.registry import Prepared, Produced, Tool, ToolRegistry
from scm_agent.types import JobRequest, JobResult


def test_job_request_defaults():
    req = JobRequest(brief="set up reorder points")
    assert req.brief == "set up reorder points"
    assert req.data_path is None
    assert req.job_type is None
    assert req.params == {}
    assert req.client == "Client"


def test_job_result_holds_status_and_deliverables():
    res = JobResult(
        status="ok",
        tool="inventory_optimization",
        confidence=0.9,
        deliverables={"report": "out/report.md"},
        summary="done",
    )
    assert res.status == "ok"
    assert res.qa_issues == []
    assert res.clarifications == []
    assert res.deliverables["report"].endswith("report.md")


def test_rules_fallback_is_unavailable_and_inert():
    p = llm.RulesFallback()
    assert p.available() is False
    assert p.complete("anything") == ""
    assert p.extract("anything", {}) == {}


def test_get_provider_without_key_returns_rules_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p = llm.get_provider()
    assert isinstance(p, llm.RulesFallback)
    assert p.available() is False


def test_parse_json_object_extracts_embedded_object():
    text = 'Sure! Here it is:\n```json\n{"job_type": "pricing", "n": 3}\n```\nThanks'
    obj = llm.parse_json_object(text)
    assert obj == {"job_type": "pricing", "n": 3}


def test_parse_json_object_returns_empty_on_garbage():
    assert llm.parse_json_object("no json here") == {}
    assert llm.parse_json_object("") == {}


def test_claude_provider_reports_available_without_network():
    # available() must not require the SDK or a network call
    p = llm.ClaudeProvider(api_key="sk-test", model="claude-opus-4-8")
    assert p.available() is True


def _dummy_tool(key, keywords, requires_data=True):
    return Tool(
        key=key, title=key.title(), description=f"{key} tool",
        intent_keywords=tuple(keywords), requires_data=requires_data,
        prepare=lambda req, prov: Prepared(status="ok", payload=None),
        run=lambda payload, params: Produced(report=None, summary="ok"),
        qa=lambda report: [],
        deliver=lambda report, out_dir, client: {},
    )


def test_registry_register_get_list():
    reg = ToolRegistry()
    t = _dummy_tool("inventory_optimization", ["reorder", "inventory"])
    reg.register(t)
    assert reg.get("inventory_optimization") is t
    assert [x.key for x in reg.list()] == ["inventory_optimization"]


def test_registry_rejects_duplicate_key():
    reg = ToolRegistry()
    reg.register(_dummy_tool("pricing", ["price"]))
    with pytest.raises(ValueError):
        reg.register(_dummy_tool("pricing", ["price"]))


def test_registry_get_unknown_raises_keyerror():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_registry_match_scores_by_keyword_hits():
    reg = ToolRegistry()
    reg.register(_dummy_tool("inventory_optimization", ["reorder", "safety stock", "inventory"]))
    reg.register(_dummy_tool("pricing", ["price", "elasticity", "margin"]))
    ranked = reg.match("set up reorder points and safety stock for my inventory")
    assert ranked[0][0].key == "inventory_optimization"
    assert ranked[0][1] >= 3  # three keyword hits
    assert ranked[1][1] == 0  # pricing has no hits


# ---------------------------------------------------------------------------
# Task 7 — tools.py
# ---------------------------------------------------------------------------

PORTFOLIO = "data/sample_demand_portfolio.csv"
PRICING_CSV = "data/sample_pricing.csv"


def test_build_default_registry_has_three_tools():
    reg = tools.build_default_registry()
    keys = {t.key for t in reg.list()}
    assert keys == {"inventory_optimization", "pricing", "leadership_chain"}
    assert reg.get("leadership_chain").requires_data is False
    assert reg.get("inventory_optimization").requires_data is True


def test_inventory_tool_pipeline_on_sample(tmp_path):
    from scm_agent import llm
    t = tools.inventory_tool()
    req = JobRequest(brief="reorder points", data_path=PORTFOLIO)
    prep = t.prepare(req, llm.RulesFallback())
    assert prep.status == "ok"
    produced = t.run(prep.payload, {})
    assert t.qa(produced.report) == []
    written = t.deliver(produced.report, tmp_path, "Acme")
    assert written["excel"].exists() and written["report"].exists()


def test_inventory_tool_reports_needs_data_when_columns_undetectable(tmp_path):
    from scm_agent import llm
    bad = tmp_path / "bad.csv"
    bad.write_text("foo,bar\n1,2\n", encoding="utf-8")
    t = tools.inventory_tool()
    prep = t.prepare(JobRequest(brief="reorder", data_path=str(bad)), llm.RulesFallback())
    assert prep.status == "needs_data"
    assert prep.messages


def test_pricing_tool_pipeline_on_sample(tmp_path):
    from scm_agent import llm
    t = tools.pricing_tool()
    prep = t.prepare(JobRequest(brief="optimal price", data_path=PRICING_CSV), llm.RulesFallback())
    assert prep.status == "ok"
    produced = t.run(prep.payload, {})
    assert t.qa(produced.report) == []
    written = t.deliver(produced.report, tmp_path, "Acme")
    assert written["excel"].exists()


def test_leadership_tool_with_scores_in_params(tmp_path):
    from scm_agent import llm
    t = tools.leadership_tool()
    req = JobRequest(brief="evaluate our SC leadership", params={"scores": "3 2 3 1 1", "name": "Equipo X"})
    prep = t.prepare(req, llm.RulesFallback())
    assert prep.status == "ok"
    produced = t.run(prep.payload, {})
    assert t.qa(produced.report) == []
    written = t.deliver(produced.report, tmp_path, "Acme")
    assert written["chart"].exists() and written["report"].exists()


def test_leadership_tool_needs_clarification_without_scores_or_llm():
    from scm_agent import llm
    t = tools.leadership_tool()
    prep = t.prepare(JobRequest(brief="how is my leadership?"), llm.RulesFallback())
    assert prep.status == "needs_clarification"
    assert len(prep.messages) >= 10  # the diagnostic questions
