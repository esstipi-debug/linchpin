"""VoiceCaller adapter (capability M16) - the dial seam.

A ``VoiceCaller`` places one outbound call from a prepared ``CallRequest`` (phone
number + deployable agent config + dynamic shipment variables) and returns a
``CallOutcome``. Two implementations ship here:

* ``DryRunCaller`` - credential-free. Logs the call it *would* place and returns a
  dry-run (or test-scripted) outcome. This is what closes the voice loop end-to-end
  without ever touching a phone network.
* ``ElevenLabsCaller`` - the credentialed seam (ElevenLabs ConvAI + Twilio). It
  refuses to dial until wired live, so importing/constructing it is always safe.

Pure adapter: no network, no credentials at import time. The orchestration in
``followup.py`` consumes this surface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

# Call statuses.
CALL_DRY_RUN = "dry_run"        # simulated; no real call placed
CALL_COMPLETED = "completed"    # call connected and ran the playbook
CALL_NO_ANSWER = "no_answer"
CALL_VOICEMAIL = "voicemail"


@dataclass(frozen=True)
class CallRequest:
    """A staged, ready-to-place call. Built by the orchestration, consumed by a caller."""

    to: str                                         # destination phone number (E.164)
    agent_config: dict                              # from build_agent_config (the deployable artifact)
    dynamic_vars: dict = field(default_factory=dict)  # volatile shipment facts (bl_no, po_no, ...)
    playbook_key: str = ""
    requires_ai_disclosure: bool = True             # always, per TCPA / EU AI Act
    requires_recording_consent: bool = False        # true in all-party-consent states


@dataclass(frozen=True)
class CallOutcome:
    """The result of (attempting) one call."""

    status: str
    placed: bool
    captured: dict = field(default_factory=dict)    # the playbook.capture data-collection fields
    transcript: str = ""
    needs_human: bool = False                       # the call surfaced an escalate_when condition
    call_id: str = ""


class VoiceCaller(Protocol):
    """Places one outbound call and returns its outcome."""

    def place(self, request: CallRequest) -> CallOutcome: ...


class DryRunCaller:
    """Credential-free caller: records the call it would place; never dials.

    With no script it returns a dry-run outcome (``placed=False``). Pass ``scripted``
    to simulate what a connected call would return - this lets the whole orchestration
    (compliance -> config -> call -> capture -> sync) be tested without credentials.
    """

    def __init__(self, scripted: CallOutcome | None = None) -> None:
        self.placed_calls: list[CallRequest] = []
        self._scripted = scripted

    def place(self, request: CallRequest) -> CallOutcome:
        self.placed_calls.append(request)
        logger.info(
            "DRY-RUN voice call -> %s [%s] (not dialed)", request.to, request.playbook_key
        )
        if self._scripted is not None:
            return self._scripted
        return CallOutcome(
            status=CALL_DRY_RUN, placed=False, call_id=f"dry-{len(self.placed_calls)}"
        )


class ElevenLabsCaller:
    """Live caller (ElevenLabs ConvAI + Twilio). Credentialed - not yet wired.

    Constructing it is safe; ``place`` raises until live dialing is implemented and
    credentials are supplied. Use ``DryRunCaller`` for credential-free runs.
    """

    def __init__(
        self, *, agent_api_key: str | None = None, phone_number_id: str | None = None
    ) -> None:
        self._agent_api_key = agent_api_key
        self._phone_number_id = phone_number_id

    def place(self, request: CallRequest) -> CallOutcome:
        raise NotImplementedError(
            "live ElevenLabs ConvAI + Twilio dialing requires credentials and is not yet "
            "wired; use DryRunCaller for credential-free runs"
        )
