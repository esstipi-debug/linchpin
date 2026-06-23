"""Tests for the ElevenLabs agent-config builder (capability M16, credential-free).

Produces the 6-block system prompt + agent config dict as an artifact — no API call.
"""

from src.voice.agent_config import GUARDRAILS, build_agent_config, build_system_prompt
from src.voice.playbooks import get_playbook


def test_system_prompt_has_all_six_blocks():
    prompt = build_system_prompt(get_playbook("eta_check"), shipper="Acme Co")
    for block in ("# Personality", "# Environment", "# Tone", "# Goal", "# Guardrails", "# Tools"):
        assert block in prompt


def test_persona_mentions_the_shipper():
    prompt = build_system_prompt(get_playbook("eta_check"), shipper="Acme Co")
    assert "Acme Co" in prompt


def test_guardrails_cover_rates_liability_and_ai_disclosure():
    text = " ".join(GUARDRAILS).lower()
    assert "rate" in text          # never quote/negotiate rates
    assert "liab" in text          # never admit liability
    assert "ai" in text            # disclose AI


def test_build_agent_config_artifact():
    cfg = build_agent_config(get_playbook("po_confirm"), shipper="Acme Co", kb_id="kb_123")
    assert cfg["system_prompt"]
    assert cfg["knowledge_base_id"] == "kb_123"
    assert cfg["voicemail_detection"] is True
    # data collection mirrors the playbook's capture fields
    assert tuple(cfg["data_collection"]) == get_playbook("po_confirm").capture
    assert cfg["language"]  # multilingual setting present


def test_goal_block_reflects_the_playbook():
    prompt = build_system_prompt(get_playbook("demurrage_check"), shipper="X")
    assert "demurrage" in prompt.lower()
