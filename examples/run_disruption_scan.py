"""Run the Supplier Disruption Exposure Scan end-to-end.

Live scan against GDELT (free, no key -- needs only a supplier list):

    python examples/run_disruption_scan.py --data suppliers.csv --client "Acme"

Offline demo (canned GDELT fixture, no network):

    python examples/run_disruption_scan.py --demo

The supplier CSV needs a supplier column; country and annual_spend are optional
but sharpen the signal (country disambiguates common names, spend scales impact).
Read-only: this never writes to any system. Source: The GDELT Project
(https://www.gdeltproject.org/).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jobs import disruption_scan_job as job  # noqa: E402


def _demo_fetcher(fixture_dir: Path):
    """Serve the canned Acme response for the flagged supplier, empty for the rest."""
    acme = (fixture_dir / "acme_electronics.json").read_text(encoding="utf-8")
    empty = (fixture_dir / "empty.json").read_text(encoding="utf-8")

    def fetch(url: str) -> str:
        return acme if "Acme" in url else empty

    return fetch


def main() -> int:
    # Supplier names can carry non-ASCII (CJK/accented) characters that a Windows
    # cp1252 console cannot encode; never let the summary print crash the scan.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="Supplier Disruption Exposure Scan (GDELT).")
    parser.add_argument("--data", help="supplier-list CSV (supplier, optional country / annual_spend)")
    parser.add_argument("--out", default="deliverables", help="output directory")
    parser.add_argument("--client", default="Client")
    parser.add_argument("--timespan", default="3m", help="GDELT lookback (e.g. 3m, 6w, 30d)")
    parser.add_argument("--demo", action="store_true", help="run offline against the canned fixture")
    args = parser.parse_args()

    if args.demo:
        root = Path(__file__).resolve().parents[1]
        rows = job.prepare(str(root / "tests" / "fixtures" / "disruption" / "suppliers.csv"))
        fetcher = _demo_fetcher(root / "tests" / "fixtures" / "gdelt")
    elif args.data:
        rows = job.prepare(args.data)
        fetcher = None  # live, throttled GDELT GET
    else:
        parser.error("pass --data <suppliers.csv> or --demo")
        return 2

    report = job.run(rows, fetcher=fetcher, timespan=args.timespan)

    issues = job.verify(report)
    if issues:
        print("QA FAILED:")
        for i in issues:
            print(f"  - {i}")
        return 1

    out_dir = Path(args.out)
    paths = job.write_operational(report, out_dir, args.client)
    deck = job.build_deck(report, client=args.client)
    deck_paths = deck.write_all(out_dir)

    print(report.summary)
    print(f"  outcome: {report.outcome.status} ({len(report.outcome.options)} option(s))")
    print(f"  operational CSV: {paths['csv']}")
    print(f"  deck report:     {deck_paths['report']}")
    print(f"  workbook:        {deck_paths['workbook']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
