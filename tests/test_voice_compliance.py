"""Tests for the outbound-call compliance gate (capability M16, credential-free).

Must pass before any dial: DNC, consent, calling window, attempt cap. Always flags
the AI-disclosure requirement (TCPA / EU AI Act) and recording consent in all-party
states.
"""

from src.voice.compliance import ComplianceDecision, can_dial


def _ok(**kw):
    base = dict(consent=True, on_dnc=False, now_local_hour=10, attempts=0)
    base.update(kw)
    return can_dial(**base)


def test_clean_call_is_allowed():
    d = _ok()
    assert isinstance(d, ComplianceDecision)
    assert d.allowed
    assert d.requires_ai_disclosure  # always


def test_dnc_blocks():
    d = _ok(on_dnc=True)
    assert not d.allowed
    assert any("dnc" in r.lower() for r in d.reasons)


def test_missing_consent_blocks():
    d = _ok(consent=False)
    assert not d.allowed
    assert any("consent" in r.lower() for r in d.reasons)


def test_outside_calling_window_blocks():
    assert not _ok(now_local_hour=6).allowed   # before 8am
    assert not _ok(now_local_hour=22).allowed   # after 9pm


def test_attempt_cap_blocks():
    d = _ok(attempts=3, max_attempts=3)
    assert not d.allowed
    assert any("attempt" in r.lower() for r in d.reasons)


def test_all_party_state_requires_recording_consent():
    assert _ok(all_party_state=True).requires_recording_consent
    assert not _ok(all_party_state=False).requires_recording_consent


def test_multiple_violations_listed_together():
    d = can_dial(consent=False, on_dnc=True, now_local_hour=3, attempts=9, max_attempts=3)
    assert not d.allowed
    assert len(d.reasons) >= 3
