"""Tests for the scm_agent orchestrator package."""

from scm_agent import llm
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
