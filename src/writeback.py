"""Safe-staging writeback control plane (capability M15).

The agent never mutates a client's system of record directly. It:
  1. STAGES a dry-run ``Changeset`` (field-level before/after) without writing;
  2. classifies it by RISK TIER (read / reversible / irreversible);
  3. requires a valid, matching, unexpired ``Approval`` for anything that is not
     auto-applicable under policy;
  4. APPLIES idempotently (the same idempotency_key never lands twice);
  5. records an AUDIT entry so any applied changeset can be ROLLED BACK.

This module is pure and ships an ``InMemoryStore`` reference implementation that
stands in for a real connector (ERP / Excel / DB). Real connectors implement the
same read/commit/rollback surface; the safety logic here is connector-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass

# Risk tiers, by reversibility/impact.
TIER_READ = "read"
TIER_REVERSIBLE = "reversible"        # a write that can be cleanly undone (e.g. set a field)
TIER_IRREVERSIBLE = "irreversible"    # a write that cannot be safely undone (e.g. send a PO)


class WritebackRefused(Exception):
    """Raised when an apply is blocked by the safety policy (missing/invalid approval)."""


def requires_approval(tier: str, *, auto_apply_reversible: bool = False) -> bool:
    """Whether a tier needs explicit human approval before it can be applied."""
    if tier == TIER_READ:
        return False
    if tier == TIER_REVERSIBLE:
        return not auto_apply_reversible
    return True  # irreversible always needs a human in the loop


@dataclass(frozen=True)
class Change:
    """A single field-level edit, as a dry-run before/after pair."""

    entity_id: str
    field: str
    before: object
    after: object

    @property
    def is_noop(self) -> bool:
        return self.before == self.after


@dataclass(frozen=True)
class Changeset:
    """A staged, not-yet-applied set of changes against one target system."""

    target: str
    changes: tuple[Change, ...]
    risk_tier: str
    idempotency_key: str
    reason: str = ""

    @property
    def is_noop(self) -> bool:
        return all(c.is_noop for c in self.changes)

    def summary(self) -> str:
        n = sum(1 for c in self.changes if not c.is_noop)
        return f"{n} change(s) to {self.target} [{self.risk_tier}] key={self.idempotency_key}"


@dataclass(frozen=True)
class Approval:
    """A time-boxed authorization bound to one changeset key."""

    changeset_key: str
    approved_by: str
    expires_at: float

    def is_valid_at(self, now: float) -> bool:
        return now < self.expires_at


@dataclass(frozen=True)
class AuditEntry:
    """What was applied, by whom, and how to undo it."""

    idempotency_key: str
    target: str
    approved_by: str
    restore: tuple[tuple[str, str, object], ...]  # (entity_id, field, original_value)


@dataclass(frozen=True)
class ApplyResult:
    applied: bool
    idempotent_skip: bool = False
    audit_id: str | None = None


def approve(changeset: Changeset, approved_by: str, *, now: float, ttl_seconds: float = 900.0) -> Approval:
    """Mint an approval valid for ``ttl_seconds`` from ``now`` (caller supplies the clock)."""
    return Approval(changeset.idempotency_key, approved_by, now + ttl_seconds)


class InMemoryStore:
    """Reference system-of-record. Real connectors mirror read/_commit/rollback."""

    def __init__(self, records: dict | None = None) -> None:
        self._records: dict[str, dict] = {k: dict(v) for k, v in (records or {}).items()}
        self._applied: dict[str, AuditEntry] = {}

    def read(self, entity_id: str) -> dict:
        return dict(self._records.get(entity_id, {}))

    def applied_keys(self) -> set[str]:
        return set(self._applied)

    def commit(self, changeset: Changeset, approved_by: str) -> AuditEntry:
        # Capture originals BEFORE writing, so rollback is exact.
        restore = tuple(
            (c.entity_id, c.field, self._records.get(c.entity_id, {}).get(c.field, _ABSENT))
            for c in changeset.changes
        )
        for c in changeset.changes:
            self._records.setdefault(c.entity_id, {})[c.field] = c.after
        entry = AuditEntry(changeset.idempotency_key, changeset.target, approved_by, restore)
        self._applied[changeset.idempotency_key] = entry
        return entry

    def rollback(self, idempotency_key: str) -> None:
        entry = self._applied.get(idempotency_key)
        if entry is None:
            raise KeyError(idempotency_key)
        for entity_id, fld, original in entry.restore:
            if original is _ABSENT:
                self._records.get(entity_id, {}).pop(fld, None)
            else:
                self._records.setdefault(entity_id, {})[fld] = original
        del self._applied[idempotency_key]


_ABSENT = object()  # sentinel: the field did not exist before the change


def stage(
    store: InMemoryStore,
    target: str,
    edits: dict[str, dict],
    *,
    risk_tier: str,
    idempotency_key: str,
    reason: str = "",
) -> Changeset:
    """Compute a dry-run Changeset from current store values. Does NOT write."""
    changes: list[Change] = []
    for entity_id, fields in edits.items():
        current = store.read(entity_id)
        for fld, after in fields.items():
            changes.append(Change(entity_id, fld, current.get(fld), after))
    return Changeset(target, tuple(changes), risk_tier, idempotency_key, reason)


def apply(
    store: InMemoryStore,
    changeset: Changeset,
    *,
    approval: Approval | None = None,
    now: float = 0.0,
    auto_apply_reversible: bool = False,
) -> ApplyResult:
    """Apply a staged changeset under the safety policy.

    Refuses (``WritebackRefused``) when approval is required but missing, bound to a
    different changeset, or expired. Idempotent on ``idempotency_key``.
    """
    if requires_approval(changeset.risk_tier, auto_apply_reversible=auto_apply_reversible):
        if (
            approval is None
            or approval.changeset_key != changeset.idempotency_key
            or not approval.is_valid_at(now)
        ):
            raise WritebackRefused(
                f"approval required for tier '{changeset.risk_tier}' and is missing/mismatched/expired"
            )

    if changeset.idempotency_key in store.applied_keys():
        return ApplyResult(applied=False, idempotent_skip=True, audit_id=changeset.idempotency_key)

    approved_by = approval.approved_by if approval is not None else "auto"
    entry = store.commit(changeset, approved_by)
    return ApplyResult(applied=True, idempotent_skip=False, audit_id=entry.idempotency_key)
