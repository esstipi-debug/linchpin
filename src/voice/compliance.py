"""Outbound-call compliance gate (capability M16).

Must pass before any dial. Checks DNC, consent, calling window, and attempt cap;
always flags the AI-disclosure requirement (FCC TCPA ruling on AI voices + EU AI Act
Art. 50) and recording-consent in all-party-consent states. Pure logic — the caller
supplies the clock (local hour) and the contact's consent/DNC/attempt state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Default permissible calling window (local time), inclusive start, exclusive end.
_DEFAULT_WINDOW = (8, 21)


@dataclass(frozen=True)
class ComplianceDecision:
    allowed: bool
    reasons: list[str] = field(default_factory=list)        # why blocked (empty if allowed)
    requires_ai_disclosure: bool = True                     # always, per TCPA / EU AI Act
    requires_recording_consent: bool = False                # true in all-party-consent states


def can_dial(
    *,
    consent: bool,
    on_dnc: bool,
    now_local_hour: int,
    attempts: int,
    max_attempts: int = 3,
    window: tuple[int, int] = _DEFAULT_WINDOW,
    all_party_state: bool = False,
) -> ComplianceDecision:
    """Decide whether an outbound call may be placed right now."""
    reasons: list[str] = []

    if on_dnc:
        reasons.append("number is on the Do-Not-Call (DNC) list")
    if not consent:
        reasons.append("no documented consent / legitimate-interest basis to call")
    start, end = window
    if not (start <= now_local_hour < end):
        reasons.append(f"outside the permitted calling window {start}:00-{end}:00 local (now {now_local_hour}:00)")
    if attempts >= max_attempts:
        reasons.append(f"attempt cap reached ({attempts}/{max_attempts})")

    return ComplianceDecision(
        allowed=not reasons,
        reasons=reasons,
        requires_ai_disclosure=True,
        requires_recording_consent=all_party_state,
    )
