"""Tests for the voice-agent call playbooks (capability M16, credential-free).

The 7 logistics call types as structured data + a renderer that turns one into the
numbered Goal-block steps the ElevenLabs system prompt uses (the "guion").
"""

import pytest

from src.voice.playbooks import (
    PLAYBOOK_KEYS,
    CallPlaybook,
    get_playbook,
    list_playbooks,
    render_goal_block,
)


def test_seven_playbooks_exist():
    keys = list_playbooks()
    assert len(keys) == 7
    assert set(keys) == set(PLAYBOOK_KEYS)


def test_get_playbook_returns_structured_flow():
    pb = get_playbook("eta_check")
    assert isinstance(pb, CallPlaybook)
    assert pb.goal
    assert pb.questions          # things to ask
    assert pb.doc_fields         # which document fields it references
    assert pb.capture            # what to record from the call
    assert pb.escalate_when      # when to hand to a human


def test_unknown_playbook_raises():
    with pytest.raises(KeyError):
        get_playbook("not_a_call_type")


def test_osd_intake_escalates_liability_to_human():
    pb = get_playbook("osd_intake")
    assert "liab" in pb.escalate_when.lower() or "human" in pb.escalate_when.lower()


def test_customs_status_escalates_to_broker():
    pb = get_playbook("customs_status")
    assert "broker" in pb.escalate_when.lower() or "classif" in pb.escalate_when.lower()


def test_render_goal_block_is_numbered_script():
    block = render_goal_block(get_playbook("delivery_appointment"))
    assert "1." in block                      # numbered steps
    assert "Escalate" in block or "escalate" in block
    # references the playbook's own questions
    q0 = get_playbook("delivery_appointment").questions[0]
    assert q0[:12] in block
