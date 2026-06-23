"""Voice agent brain (capability M16) — the credential-free core.

Everything here is pure logic the agent needs to converse competently with carriers
and suppliers: the per-call-type playbooks (the "guion"), the compliance gate that
must pass before any dial, the logistics document field maps, and the ElevenLabs
agent-config builder. Placing the actual call (ElevenLabs ConvAI + Twilio) and live
Anthropic document reading are the only parts that need credentials; this package is
built and tested without them.
"""
