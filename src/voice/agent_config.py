"""ElevenLabs agent-config builder (capability M16, credential-free).

Assembles the six-block system prompt (Personality, Environment, Tone, Goal,
Guardrails, Tools) and the agent config dict as an *artifact* — no API call, no
credentials. Deploying it (POST to ElevenLabs ConvAI) is the only credentialed step.
Goal is the playbook's rendered script; general logistics knowledge comes from the
RAG knowledge base; volatile shipment facts come from dynamic variables / server tools.
"""

from __future__ import annotations

from .playbooks import CallPlaybook, render_goal_block

# Cross-cutting guardrails applied to every call (research §6 + compliance).
GUARDRAILS = (
    "Disclose at the start of the call that you are an AI assistant calling on behalf of the shipper.",
    "Announce the call is recorded and obtain consent before proceeding.",
    "Never quote, negotiate, or commit to freight rates or prices.",
    "Never admit liability or offer a settlement; for damage/disputes, only intake the facts.",
    "Never give customs classification or duty advice; route those to a licensed broker.",
    "Confirm the contact's identity before sharing shipment PII.",
    "Hand off to a human on any dispute, money commitment, or legal exposure.",
)

# Server tools the agent calls mid-conversation for live, shipment-specific truth.
_DEFAULT_TOOLS = (
    "lookup_shipment_status",   # queries the TMS/tracking + L3 graph for live status
    "lookup_document_field",    # returns a value extracted from a logistics document
)

_PERSONALITY = (
    "You are an experienced freight coordinator calling on behalf of {shipper}. "
    "You are calm, concise, and fluent in logistics terminology (Incoterms, ETD/ETA, "
    "demurrage vs detention, FCL/LCL, drayage, OS&D, accessorials)."
)
_ENVIRONMENT = (
    "You are on an outbound phone call with a carrier, freight forwarder, 3PL, or supplier. "
    "Background knowledge (Incoterms, free-time rules, container types, glossary) is in your "
    "knowledge base; specific shipment facts arrive as dynamic variables and live tool lookups."
)
_TONE = (
    "Professional and brief. One question at a time. Confirm numbers by reading them back. "
    "Never speak a container/B-L/AWB number you have not verified."
)


def build_system_prompt(
    playbook: CallPlaybook,
    *,
    shipper: str,
    language: str = "multilingual (31 languages; detect and match the callee)",
) -> str:
    """Assemble the six-block ElevenLabs system prompt for one call type."""
    blocks = [
        "# Personality\n" + _PERSONALITY.format(shipper=shipper),
        "# Environment\n" + _ENVIRONMENT + f"\nLanguage: {language}.",
        "# Tone\n" + _TONE,
        render_goal_block(playbook),  # already starts with "# Goal — ..."
        "# Guardrails\n" + "\n".join(f"- {g}" for g in GUARDRAILS),
        "# Tools\n" + "\n".join(f"- {t}" for t in _DEFAULT_TOOLS),
    ]
    return "\n\n".join(blocks)


def build_agent_config(
    playbook: CallPlaybook,
    *,
    shipper: str,
    kb_id: str | None = None,
    tools: tuple[str, ...] = _DEFAULT_TOOLS,
    language: str = "multilingual (31 languages; detect and match the callee)",
) -> dict:
    """Build the deployable ElevenLabs agent config artifact for one call type."""
    return {
        "name": f"linchpin-logistics-{playbook.key}",
        "system_prompt": build_system_prompt(playbook, shipper=shipper, language=language),
        "language": language,
        "knowledge_base_id": kb_id,
        "tools": list(tools),
        "voicemail_detection": True,
        "data_collection": list(playbook.capture),  # post-call structured capture
        "guardrails": list(GUARDRAILS),
    }
