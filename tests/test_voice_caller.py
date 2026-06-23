"""Tests for the VoiceCaller adapter (capability M16, credential-free).

The DryRunCaller closes the voice loop without credentials: it logs the call it
*would* place and returns a (optionally scripted) CallOutcome. The ElevenLabsCaller
is the credentialed seam - it refuses to dial until wired live.
"""

import pytest

from src.voice.agent_config import build_agent_config
from src.voice.caller import (
    CALL_DRY_RUN,
    CallOutcome,
    CallRequest,
    DryRunCaller,
    ElevenLabsCaller,
)
from src.voice.playbooks import get_playbook


def _request(**kw):
    cfg = build_agent_config(get_playbook("eta_check"), shipper="Acme")
    base = dict(
        to="+15551234567",
        agent_config=cfg,
        dynamic_vars={"bl_no": "BL1"},
        playbook_key="eta_check",
    )
    base.update(kw)
    return CallRequest(**base)


def test_dry_run_caller_logs_the_call_it_would_place():
    caller = DryRunCaller()
    req = _request()

    out = caller.place(req)

    assert caller.placed_calls == [req]  # logged, never dialed
    assert out.placed is False
    assert out.status == CALL_DRY_RUN


def test_dry_run_caller_returns_scripted_outcome_when_provided():
    scripted = CallOutcome(status="completed", placed=True, captured={"new_eta": "2026-07-01"})
    caller = DryRunCaller(scripted=scripted)

    out = caller.place(_request())

    assert out is scripted
    assert out.captured["new_eta"] == "2026-07-01"
    assert len(caller.placed_calls) == 1  # still logged


def test_dry_run_caller_assigns_distinct_call_ids():
    caller = DryRunCaller()

    a = caller.place(_request())
    b = caller.place(_request())

    assert a.call_id and b.call_id and a.call_id != b.call_id


def test_elevenlabs_caller_refuses_until_credentialed():
    caller = ElevenLabsCaller()

    with pytest.raises(NotImplementedError):
        caller.place(_request())


def test_call_outcome_defaults_are_safe():
    out = CallOutcome(status=CALL_DRY_RUN, placed=False)

    assert out.captured == {}
    assert out.needs_human is False
    assert out.transcript == ""
    assert out.call_id == ""


def test_call_request_carries_the_playbook_agent_config():
    req = _request()

    assert req.agent_config["name"] == "linchpin-logistics-eta_check"
    assert req.dynamic_vars == {"bl_no": "BL1"}
    assert req.requires_ai_disclosure is True  # safe default
