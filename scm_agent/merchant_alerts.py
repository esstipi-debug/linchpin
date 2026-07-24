"""Merchant-facing alert rendering -- the delivery half of **Kern Alerts**
(the self-serve monitoring product, ``documentation/MONETIZATION_BRIEF.md``
addendum #2 / ``scm_agent/monitors.py``'s A1 "sense" layer).

Kern's existing notification path (``jobs/notify.py``) posts to an OPERATOR's
Slack webhook: it is an internal ops signal, not something a paying merchant
ever sees. Kern Alerts needs the opposite -- a message written FOR the
merchant, in plain language, with a suggested reorder quantity and a mandatory
"this is a suggestion, verify before ordering" disclaimer on every send.

This module is that renderer, and nothing more. It is a **pure function** over
already-emitted :class:`~scm_agent.events.Event` objects (the output of
``scm_agent.monitors.run_all_monitors``): it never reads state, never writes
anything back, never sends anything. Rendering is separated from transport on
purpose -- the concierge phase of Kern Alerts (MONETIZATION_BRIEF §7, Fase 1)
is explicitly "email semiautomatico": an operator reviews the rendered
:class:`MerchantAlert` and sends it, so the honest primitive is the message,
not an autonomous mailer. A later phase-2 transport can consume the exact same
:class:`MerchantAlert` unchanged.

**Suggestion, never execution** (MONETIZATION_BRIEF §1, the frontier that
protects the whole pricing ladder): every line here is text. No PO is staged,
no ERP is touched, no writeback module is imported. Kern Alerts sits entirely
in autonomy tier T1 -- it calculates the number and shows it; the merchant
decides and orders. That red line is what makes Alerts a $49-99/mes self-serve
product instead of the $1,500+/mes human-in-the-loop tiers.

**Scope of v1** (MONETIZATION_BRIEF §3): exactly the three inventory monitors
wired to routing in ``config/event_routing.yaml`` -- ``rop_breach``,
``stockout_projected``, ``excess_growing``. Every other event type reaching
this renderer (``competitor_price_move``, the two un-routed forecast/lead-time
monitors, anything else) is silently ignored: those are not part of the Kern
Alerts merchant surface in v1, and surfacing them here would leak
higher-tier / operator-only signals into a self-serve product.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .events import Event

# The three monitor event types Kern Alerts v1 surfaces to a merchant. Kept in
# lockstep with config/event_routing.yaml's routed inventory monitors and
# scm_agent/monitors.py's EVENT_* constants -- NOT the un-routed
# forecast_error_out_of_band / lead_time_drift (no honest merchant action yet)
# nor competitor_price_move (a higher-tier price-intel signal, not inventory).
ALERTS_V1_EVENT_TYPES: frozenset[str] = frozenset(
    {"rop_breach", "stockout_projected", "excess_growing"}
)

# Mandatory on every merchant-facing send (MONETIZATION_BRIEF §3). ASCII-only
# so it survives a Windows cp1252 console print unchanged (repo gotcha).
DISCLAIMER = "Sugerencia calculada por Kern -- verifica antes de ordenar."

# Severity ordering for presentation (most urgent first), mirroring
# src/alerting.py's own _SEVERITY_RANK. Unknown severities sort last.
_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# Human-readable, merchant-facing label per event type (Spanish, the Kern
# Alerts / LatAm surface language). Deliberately plain -- no jargon.
_TYPE_LABEL = {
    "stockout_projected": "Quiebre de stock inminente",
    "rop_breach": "Llego al punto de reorden",
    "excess_growing": "Exceso de inventario creciendo",
}


@dataclass(frozen=True)
class AlertLine:
    """One rendered merchant-facing alert for one SKU.

    ``suggested_order_qty`` is the quantity needed to climb back to the SKU's
    reorder point (``max(reorder_point - on_hand, 0)``, rounded up), and is
    populated ONLY for replenishment events (``rop_breach`` /
    ``stockout_projected``) where ordering more is the correct action. It is
    ``None`` for ``excess_growing`` -- ordering more of an already-excess SKU
    is exactly the wrong move, so no buy quantity is ever suggested there.
    Deliberately a floor-to-reorder-point figure, honestly labelled as such in
    :meth:`to_text`: the fuller order-up-to-S quantity lives in the paid tiers'
    ``inventory_optimization`` tool, not in a self-serve alert.
    """

    sku: str
    event_type: str
    severity: str
    message: str
    suggested_order_qty: int | None = None

    def to_text(self) -> str:
        label = _TYPE_LABEL.get(self.event_type, self.event_type)
        head = f"[{self.severity.upper()}] {self.sku} -- {label}"
        if self.suggested_order_qty is not None:
            head += f" | Sugerido pedir ~{self.suggested_order_qty} u. para volver al punto de reorden"
        return head


@dataclass(frozen=True)
class MerchantAlert:
    """A merchant-ready alert digest: a subject line, a plain-text body ending
    in the mandatory :data:`DISCLAIMER`, and the counts an operator (or a
    later transport) needs to decide whether it is even worth sending.

    ``alert_count == 0`` is a valid, first-class result -- a quiet inventory
    is good news, and the concierge operator can choose to send a "todo en
    orden" note or skip the cycle entirely. The body still carries no
    fabricated urgency in that case.
    """

    merchant_name: str
    subject: str
    body: str
    lines: tuple[AlertLine, ...] = field(default_factory=tuple)
    alert_count: int = 0
    high_severity_count: int = 0

    @property
    def is_empty(self) -> bool:
        return self.alert_count == 0


def _suggested_order_qty(event: Event) -> int | None:
    """Floor-to-reorder-point buy quantity from the event's state row, or
    ``None`` when it cannot be computed honestly (missing fields, non-numeric
    values, or a non-replenishment event type). Never guesses."""
    if event.type not in {"rop_breach", "stockout_projected"}:
        return None
    rows = event.payload.get("rows") or []
    if not rows:
        return None
    row = rows[0]
    try:
        reorder_point = float(row["reorder_point"])
        on_hand = float(row["on_hand"])
    except (KeyError, TypeError, ValueError):
        return None
    gap = reorder_point - on_hand
    if gap <= 0:
        return 0
    return int(math.ceil(gap))


def _alert_line(event: Event) -> AlertLine:
    return AlertLine(
        sku=event.sku or "(sin SKU)",
        event_type=event.type,
        severity=event.severity,
        message=str(event.payload.get("message", "")),
        suggested_order_qty=_suggested_order_qty(event),
    )


def render_merchant_alert(events: list[Event], *, merchant_name: str) -> MerchantAlert:
    """Render Kern Alerts v1 :class:`~scm_agent.events.Event` objects into one
    merchant-ready :class:`MerchantAlert`.

    Only :data:`ALERTS_V1_EVENT_TYPES` are considered; every other event is
    ignored (see the module docstring for why). Surviving alerts are ordered
    most-urgent-first by severity, then by SKU for a stable, deterministic
    body. The body always ends with the mandatory :data:`DISCLAIMER`, even
    when empty (an empty digest still explains itself rather than sending a
    blank message).

    Pure: reads nothing, writes nothing, sends nothing -- the returned object
    is the whole result, for an operator or a later transport to act on.
    """
    relevant = [e for e in events if e.type in ALERTS_V1_EVENT_TYPES]
    relevant.sort(key=lambda e: (_SEVERITY_RANK.get(e.severity, 99), e.sku or ""))
    lines = tuple(_alert_line(e) for e in relevant)
    high = sum(1 for line in lines if line.severity == "high")

    if not lines:
        subject = f"Kern Alerts: sin alertas de inventario para {merchant_name}"
        body = (
            f"Hola {merchant_name},\n\n"
            "En esta corrida no se detectaron alertas de inventario "
            "(punto de reorden, quiebre proyectado ni exceso creciente).\n\n"
            f"{DISCLAIMER}"
        )
        return MerchantAlert(
            merchant_name=merchant_name,
            subject=subject,
            body=body,
            lines=lines,
            alert_count=0,
            high_severity_count=0,
        )

    urgent = f" ({high} urgente{'s' if high != 1 else ''})" if high else ""
    subject = f"Kern Alerts: {len(lines)} alerta{'s' if len(lines) != 1 else ''} de inventario{urgent} para {merchant_name}"
    body_lines = [f"Hola {merchant_name},\n", "Alertas de inventario de esta corrida:\n"]
    body_lines += [f"  - {line.to_text()}" for line in lines]
    body_lines.append("")
    body_lines.append(DISCLAIMER)
    body = "\n".join(body_lines)

    return MerchantAlert(
        merchant_name=merchant_name,
        subject=subject,
        body=body,
        lines=lines,
        alert_count=len(lines),
        high_severity_count=high,
    )
