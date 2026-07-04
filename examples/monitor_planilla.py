"""Recurring planilla monitor: re-plan, diff against the last snapshot, report deltas.

The weekly-service loop over the client's own Excel file - what changed, not the
whole plan again:

    python examples/monitor_planilla.py --file planilla_cliente.xlsx --label week-27

First run saves the baseline snapshot; every later run writes a Markdown delta
report (newly-below-target SKUs first) and advances the snapshot. Schedule it with
the OS (Windows Task Scheduler / cron) for a standing weekly cadence. Read-only:
nothing is ever written to the client's file (apply stays a separate, human
decision via examples/apply_replenishment.py).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Make repo packages importable no matter where this script is launched from.
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from jobs import excel_replenishment_job as job  # noqa: E402
from src.replenishment_delta import compare, render_markdown, snapshot  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Monitor a planilla: re-plan, diff vs last run, report deltas.")
    p.add_argument("--file", required=True, help="the client's inventory Excel file (.xlsx/.xlsm)")
    p.add_argument("--label", default="current", help="name for this run in the report (e.g. week-27)")
    p.add_argument("--state", default=None,
                   help="snapshot file (default: <file dir>/.linchpin-monitor/<name>.snapshot.json)")
    p.add_argument("--report-out", default=None,
                   help="delta report path (default: next to the snapshot, <name>.delta.md)")
    p.add_argument("--client", default="Client", help="client name for the report heading")
    p.add_argument("--sheet", default=None)
    p.add_argument("--cover-periods", type=float, default=8.0)
    p.add_argument("--order-up-to-factor", type=float, default=2.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    file_path = Path(args.file)
    state = Path(args.state) if args.state else (
        file_path.parent / ".linchpin-monitor" / f"{file_path.stem}.snapshot.json")
    report_out = Path(args.report_out) if args.report_out else state.with_name(f"{file_path.stem}.delta.md")

    params: dict = {}
    if args.sheet:
        params["sheet"] = args.sheet
    try:
        payload = job.prepare(str(file_path), params)
        report = job.run(payload, cover_periods=args.cover_periods,
                         order_up_to_factor=args.order_up_to_factor)
    except (ValueError, FileNotFoundError) as exc:
        print(f"cannot plan: {exc}")
        return 1

    curr = snapshot(report, label=args.label)
    if state.exists():
        try:
            prev = json.loads(state.read_text(encoding="utf-8"))
            delta = compare(prev, curr)
        except ValueError as exc:
            print(f"cannot diff against the stored snapshot: {exc}")
            return 1
        print(delta.summary)
        for sku, qty in delta.new_orders:
            print(f"  NEW below target: {sku} (order {qty:g})")
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(render_markdown(delta, client=args.client), encoding="utf-8")
        print(f"delta report: {report_out}")
    else:
        print(f"baseline saved ({report.n_skus} SKU(s), {report.n_restock} below target) - "
              "the next run will report deltas.")

    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps(curr, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
