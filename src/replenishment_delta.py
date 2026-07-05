"""Run-over-run replenishment deltas — the recurring-monitoring core.

A one-off plan tells a client everything once; a weekly service tells them what
CHANGED: which SKUs newly fell below target, which recovered, which order
quantities moved. This module is the pure half: ``snapshot()`` turns an
``ExcelReplenishmentReport`` (duck-typed) into a JSON-able dict, ``compare()``
diffs two snapshots, ``render_markdown()`` writes the client-facing note.
Deterministic — labels are caller-supplied, the clock is never read.
"""

from __future__ import annotations

from dataclasses import dataclass

SNAPSHOT_VERSION = 1


def snapshot(report, *, label: str = "current") -> dict:
    """JSON-able snapshot of a replenishment run (works for any report exposing
    ``filename/sheet/mode`` and ``lines`` of sku/on_hand/target/restock_qty)."""
    return {
        "version": SNAPSHOT_VERSION,
        "label": label,
        "filename": report.filename,
        "sheet": report.sheet,
        "mode": report.mode,
        "lines": [
            {"sku": ln.sku, "on_hand": ln.on_hand, "target": ln.target, "restock_qty": ln.restock_qty}
            for ln in report.lines
        ],
    }


@dataclass(frozen=True)
class DeltaReport:
    prev_label: str
    curr_label: str
    new_orders: tuple[tuple[str, float], ...]        # newly below target (sku, qty)
    resolved: tuple[str, ...]                        # were short, now covered
    qty_up: tuple[tuple[str, float, float], ...]     # (sku, prev_qty, curr_qty)
    qty_down: tuple[tuple[str, float, float], ...]
    added_skus: tuple[str, ...]
    removed_skus: tuple[str, ...]
    still_short: int                                 # SKUs below target in the current run
    summary: str

    @property
    def has_changes(self) -> bool:
        return bool(self.new_orders or self.resolved or self.qty_up or self.qty_down
                    or self.added_skus or self.removed_skus)


def _lines_by_sku(snap: dict) -> dict[str, dict]:
    return {ln["sku"]: ln for ln in snap.get("lines", [])}


def _check_version(snap: dict) -> None:
    v = snap.get("version", 1)
    if v > SNAPSHOT_VERSION:
        raise ValueError(
            f"snapshot version {v} is newer than this code understands ({SNAPSHOT_VERSION}) - "
            "refusing to reinterpret it"
        )


def compare(prev: dict, curr: dict) -> DeltaReport:
    """Diff two snapshots of the same planilla, ordered for a human reader."""
    _check_version(prev)
    _check_version(curr)
    p, c = _lines_by_sku(prev), _lines_by_sku(curr)

    new_orders: list[tuple[str, float]] = []
    resolved: list[str] = []
    qty_up: list[tuple[str, float, float]] = []
    qty_down: list[tuple[str, float, float]] = []
    for sku, line in c.items():
        curr_qty = float(line.get("restock_qty", 0.0))
        prev_line = p.get(sku)
        prev_qty = float(prev_line.get("restock_qty", 0.0)) if prev_line else 0.0
        if curr_qty > 0 and prev_qty == 0:
            new_orders.append((sku, curr_qty))
        elif curr_qty == 0 and prev_qty > 0:
            resolved.append(sku)
        elif curr_qty > 0 and prev_qty > 0 and curr_qty != prev_qty:
            (qty_up if curr_qty > prev_qty else qty_down).append((sku, prev_qty, curr_qty))

    added = tuple(sorted(set(c) - set(p)))
    removed = tuple(sorted(set(p) - set(c)))
    still_short = sum(1 for line in c.values() if float(line.get("restock_qty", 0.0)) > 0)

    prev_label = str(prev.get("label", "previous"))
    curr_label = str(curr.get("label", "current"))
    if not (new_orders or resolved or qty_up or qty_down or added or removed):
        summary = f"{prev_label} -> {curr_label}: no changes; {still_short} SKU(s) still below target."
    else:
        bits = []
        if new_orders:
            bits.append(f"{len(new_orders)} SKU(s) NEWLY below target")
        if resolved:
            bits.append(f"{len(resolved)} recovered")
        if qty_up or qty_down:
            bits.append(f"{len(qty_up) + len(qty_down)} quantity change(s)")
        if added or removed:
            bits.append(f"{len(added)} added / {len(removed)} removed SKU(s)")
        summary = f"{prev_label} -> {curr_label}: " + "; ".join(bits) + f"; {still_short} below target now."

    return DeltaReport(
        prev_label=prev_label,
        curr_label=curr_label,
        new_orders=tuple(sorted(new_orders)),
        resolved=tuple(sorted(resolved)),
        qty_up=tuple(sorted(qty_up)),
        qty_down=tuple(sorted(qty_down)),
        added_skus=added,
        removed_skus=removed,
        still_short=still_short,
        summary=summary,
    )


def render_markdown(delta: DeltaReport, *, client: str = "Client") -> str:
    """The client-facing weekly note: only what moved, most urgent first."""
    lines = [
        f"# Inventory monitor - {client}",
        "",
        f"**{delta.prev_label} -> {delta.curr_label}**: {delta.summary}",
        "",
    ]
    if delta.new_orders:
        lines += ["## Newly below target (act on these)", ""]
        lines += [f"- **{sku}**: order {qty:g}" for sku, qty in delta.new_orders]
        lines.append("")
    if delta.qty_up:
        lines += ["## Getting worse (order size grew)", ""]
        lines += [f"- {sku}: {prev:g} -> {curr:g}" for sku, prev, curr in delta.qty_up]
        lines.append("")
    if delta.qty_down:
        lines += ["## Improving (order size shrank)", ""]
        lines += [f"- {sku}: {prev:g} -> {curr:g}" for sku, prev, curr in delta.qty_down]
        lines.append("")
    if delta.resolved:
        lines += ["## Recovered (no longer below target)", ""]
        lines += [f"- {sku}" for sku in delta.resolved]
        lines.append("")
    if delta.added_skus or delta.removed_skus:
        lines += ["## Catalog changes", ""]
        lines += [f"- added: {sku}" for sku in delta.added_skus]
        lines += [f"- removed: {sku}" for sku in delta.removed_skus]
        lines.append("")
    if not delta.has_changes:
        lines += ["Nothing moved since the last check.", ""]
    return "\n".join(lines)
