"""Tests for jobs/excel_replenishment_job.py — replenish a client's planilla.

Mirrors the odoo_replenishment shape: prepare reads the system of record (here
the client's Excel file), run plans the restock and STAGES the write-back as a
dry-run changeset through the safe-staging plane, and the outcome is >=2 ranked
executable options. Nothing is ever written without an approval + apply.
"""

from __future__ import annotations

import pytest
from openpyxl import Workbook, load_workbook

from jobs import excel_replenishment_job as job
from src import writeback
from src.guided import OPTIONS, passed_guided

SHEET = "Stock Bodega"


def _make_planilla(path, *, demand_column=False, order_column=False):
    """Client-style planilla: title row, Spanish headers at row 3, own formulas."""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws["A1"] = "INVENTARIO BODEGA CENTRAL"
    headers = ["Codigo", "Descripcion", "Stock", "Punto Reorden"]
    if demand_column:
        headers.append("Demanda Semanal")
    if order_column:
        headers.append("Pedir (Linchpin)")
    for col, h in enumerate(headers, 1):
        ws.cell(row=3, column=col, value=h)
    rows = [
        ("SKU-001", "Tornillo 3mm", 42, 50, 10.0),
        ("SKU-002", "Tuerca 3mm", 130, 80, 12.0),
        ("SKU-003", "Arandela", 8, 25, 4.0),
    ]
    for r, (code, desc, stock, rop, demand) in enumerate(rows, 4):
        ws.cell(row=r, column=1, value=code)
        ws.cell(row=r, column=2, value=desc)
        ws.cell(row=r, column=3, value=stock)
        ws.cell(row=r, column=4, value=rop)
        if demand_column:
            ws.cell(row=r, column=5, value=demand)
    wb.save(path)
    return path


@pytest.fixture
def planilla(tmp_path):
    return _make_planilla(tmp_path / "planilla.xlsx")


# ---- prepare: sheet + column auto-detection ---------------------------------------

def test_prepare_autodetects_sheet_and_spanish_columns(planilla):
    payload = job.prepare(str(planilla), {})
    assert payload["sheet"] == SHEET
    assert payload["mode"] == "reorder-point"
    skus = [row.sku for row in payload["rows"]]
    assert skus == ["SKU-001", "SKU-002", "SKU-003"]
    assert payload["rows"][0].on_hand == 42
    assert payload["rows"][0].reorder_point == 50


def test_prepare_prefers_demand_mode_when_demand_column_present(tmp_path):
    p = _make_planilla(tmp_path / "d.xlsx", demand_column=True)
    payload = job.prepare(str(p), {})
    assert payload["mode"] == "demand-cover"
    assert payload["rows"][0].demand_per_period == 10.0


def test_prepare_respects_explicit_column_params(planilla):
    payload = job.prepare(str(planilla), {"sku_column": "Codigo", "stock_column": "Stock",
                                          "rop_column": "Punto Reorden", "sheet": SHEET})
    assert payload["sheet"] == SHEET
    assert len(payload["rows"]) == 3


def test_prepare_fails_clearly_without_sku_column(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Cosa", "Cantidad"])
    ws.append(["x", 1])
    f = tmp_path / "bad.xlsx"
    wb.save(f)
    with pytest.raises(ValueError, match="SKU"):
        job.prepare(str(f), {})


def test_prepare_fails_clearly_without_rop_or_demand(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.append(["Codigo", "Stock"])
    ws.append(["SKU-1", 5])
    f = tmp_path / "no_signal.xlsx"
    wb.save(f)
    with pytest.raises(ValueError, match="reorder point|demand"):
        job.prepare(str(f), {})


# ---- run: plan + staged changeset ---------------------------------------------------

def test_run_reorder_point_mode_orders_up_to_factor(planilla):
    payload = job.prepare(str(planilla), {})
    report = job.run(payload)
    # SKU-001: 42 < 50 -> order up to 2*50 => +58; SKU-002: 130 >= 80 -> 0;
    # SKU-003: 8 < 25 -> +42.
    assert report.restock == {"SKU-001": 58.0, "SKU-003": 42.0}
    assert report.n_restock == 2 and report.n_skus == 3
    assert report.total_restock == 100.0


def test_run_demand_cover_mode_targets_cover_periods(tmp_path):
    p = _make_planilla(tmp_path / "d.xlsx", demand_column=True)
    payload = job.prepare(str(p), {})
    report = job.run(payload, cover_periods=8.0)
    # SKU-001: target 80 vs 42 -> +38; SKU-002: 96 vs 130 -> 0; SKU-003: 32 vs 8 -> +24.
    assert report.restock == {"SKU-001": 38.0, "SKU-003": 24.0}
    assert report.mode == "demand-cover"


def test_run_stages_changeset_with_new_order_column(planilla):
    payload = job.prepare(str(planilla), {})
    report = job.run(payload)
    cs = report.changeset
    assert cs is not None and cs.risk_tier == writeback.TIER_REVERSIBLE
    edits = {c.field: c.after for c in cs.changes}
    # New column E: header at the header row + one qty per restocked SKU.
    assert edits["E3"] == "Pedir (Linchpin)"
    assert edits["E4"] == 58.0 and edits["E6"] == 42.0
    # Order-column cells are fresh writes (before None); the plan's INPUT cells
    # travel as no-op GUARDS (before == after) so input drift is caught at apply.
    by_field = {c.field: c for c in cs.changes}
    assert by_field["E4"].before is None
    assert by_field["C4"].before == 42 and by_field["C4"].after == 42   # stock guard
    assert by_field["D4"].before == 50 and by_field["D4"].after == 50   # ROP guard
    assert load_workbook(planilla)[SHEET]["E4"].value is None  # file untouched


def test_run_reuses_existing_order_column(tmp_path):
    p = _make_planilla(tmp_path / "o.xlsx", order_column=True)
    payload = job.prepare(str(p), {})
    report = job.run(payload)
    edits = {c.field: c.after for c in report.changeset.changes}
    assert "E3" not in edits  # header already exists -> not re-written
    assert edits["E4"] == 58.0


def test_run_no_restock_needed_stages_nothing(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["Codigo", "Stock", "Punto Reorden"])
    ws.append(["SKU-1", 100, 10])
    f = tmp_path / "full.xlsx"
    wb.save(f)
    report = job.run(job.prepare(str(f), {}))
    assert report.restock == {} and report.changeset is None
    assert report.outcome.status == OPTIONS  # still a protected, ranked outcome


# ---- outcome contract ----------------------------------------------------------------

def test_outcome_offers_ranked_executable_options(planilla):
    report = job.run(job.prepare(str(planilla), {}))
    out = report.outcome
    assert out.status == OPTIONS
    assert len(out.options) >= 2
    assert sum(1 for o in out.options if o.recommended) == 1
    assert all(o.action for o in out.options)
    assert passed_guided(out)


# ---- the loop actually closes: approve + apply the staged changeset -------------------

def test_staged_changeset_applies_to_the_real_file_with_approval(planilla):
    payload = job.prepare(str(planilla), {})
    report = job.run(payload)
    store = payload["store"]
    approval = writeback.approve(report.changeset, "operator")
    result = writeback.apply(store, report.changeset, approval=approval)
    assert result.applied
    ws = load_workbook(planilla)[SHEET]
    assert ws["E3"].value == "Pedir (Linchpin)"
    assert ws["E4"].value == 58.0
    assert ws["A1"].value == "INVENTARIO BODEGA CENTRAL"  # client content intact
    # And it is rollback-able, honoring the writeback contract end to end.
    store.rollback(report.changeset.idempotency_key)
    assert load_workbook(planilla)[SHEET]["E4"].value is None


# ---- verify / deliverables -------------------------------------------------------------

def test_verify_passes_on_good_report(planilla):
    report = job.run(job.prepare(str(planilla), {}))
    assert job.verify(report) == []


def test_verify_flags_empty_planilla(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["Codigo", "Stock", "Punto Reorden"])
    f = tmp_path / "empty.xlsx"
    wb.save(f)
    with pytest.raises(ValueError, match="no usable SKU rows"):
        job.prepare(str(f), {})


# ---- adversarial-review regressions ------------------------------------------------

def test_blank_rop_row_is_excluded_not_zeroed(tmp_path):
    # A blank ROP must never coalesce to 0: with negative stock that would place a
    # spurious order, and with positive stock it silently never replenishes.
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["Codigo", "Stock", "Punto Reorden"])
    ws.append(["SKU-OK", 8, 25])
    ws.append(["SKU-BLANK", -5, None])
    f = tmp_path / "blank_rop.xlsx"
    wb.save(f)
    report = job.run(job.prepare(str(f), {}))
    assert report.restock == {"SKU-OK": 42.0}      # no spurious order for SKU-BLANK
    assert report.n_unplanned == 1
    assert "NOT planned" in report.summary          # surfaced, never silent


def test_duplicate_skus_fail_closed(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["Codigo", "Stock", "Punto Reorden"])
    ws.append(["SKU-001", 8, 25])
    ws.append(["SKU-001", 3, 25])
    f = tmp_path / "dup.xlsx"
    wb.save(f)
    with pytest.raises(ValueError, match="duplicate SKU"):
        job.prepare(str(f), {})


def test_all_formula_stock_gives_actionable_error(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["Codigo", "Stock", "Punto Reorden"])
    ws.append(["SKU-001", "=Z1+Z2", 25])  # formula with no cached value
    f = tmp_path / "formulas.xlsx"
    wb.save(f)
    with pytest.raises(ValueError, match="formula"):
        job.prepare(str(f), {})


def test_corrupt_xlsx_raises_value_error_not_library_internals(tmp_path):
    f = tmp_path / "fake.xlsx"
    f.write_bytes(b"this is not a zip archive at all")
    with pytest.raises(ValueError, match="could not open"):
        job.prepare(str(f), {})


def test_column_binding_is_priority_ordered_not_hash_ordered(tmp_path):
    # Two stock-candidate labels in the same header row: "stock" outranks
    # "existencias" in the priority tuple, deterministically.
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(["Codigo", "Existencias", "Stock", "Punto Reorden"])
    ws.append(["SKU-001", 999, 8, 25])
    f = tmp_path / "two_labels.xlsx"
    wb.save(f)
    payload = job.prepare(str(f), {})
    assert payload["rows"][0].on_hand == 8  # bound to "Stock", not "Existencias"


def test_sheet_scan_skips_leading_catalog_sheet(tmp_path):
    # A first sheet with a SKU column but no stock must not block a later sheet
    # that fully qualifies.
    wb = Workbook()
    catalog = wb.active
    catalog.title = "Catalogo"
    catalog.append(["Codigo", "Precio"])
    catalog.append(["SKU-001", 9.99])
    inv = wb.create_sheet(SHEET)
    inv.append(["Codigo", "Stock", "Punto Reorden"])
    inv.append(["SKU-001", 8, 25])
    f = tmp_path / "multi.xlsx"
    wb.save(f)
    payload = job.prepare(str(f), {})
    assert payload["sheet"] == SHEET


def test_idempotency_key_is_content_derived_and_stable(planilla):
    r1 = job.run(job.prepare(str(planilla), {}))
    r2 = job.run(job.prepare(str(planilla), {}))
    assert r1.changeset.idempotency_key == r2.changeset.idempotency_key  # same plan
    r3 = job.run(job.prepare(str(planilla), {}), order_up_to_factor=3.0)
    assert r3.changeset.idempotency_key != r1.changeset.idempotency_key  # new plan


def test_second_week_apply_does_not_collide_with_first(planilla):
    # Week 1: plan + apply. Week 2: stock moved, a NEW plan must apply cleanly
    # (no idempotent skip, no crash-window tripwire false positive).
    p1 = job.prepare(str(planilla), {})
    r1 = job.run(p1)
    writeback.apply(p1["store"], r1.changeset, approval=writeback.approve(r1.changeset, "op"))
    wb = load_workbook(planilla)
    wb[SHEET]["C4"] = 20  # week passes; stock drops further
    wb.save(planilla)
    p2 = job.prepare(str(planilla), {})
    r2 = job.run(p2)
    assert r2.changeset.idempotency_key != r1.changeset.idempotency_key
    result = writeback.apply(p2["store"], r2.changeset, approval=writeback.approve(r2.changeset, "op"))
    assert result.applied and not result.idempotent_skip
    assert load_workbook(planilla)[SHEET]["E4"].value == 80.0  # 2*50 - 20


def test_input_drift_between_stage_and_apply_is_refused(planilla):
    from src.connectors.excel import ExcelWritebackError

    payload = job.prepare(str(planilla), {})
    report = job.run(payload)
    wb = load_workbook(planilla)
    wb[SHEET]["C4"] = 49  # stock changed AFTER staging -> the plan's qty is stale
    wb.save(planilla)
    with pytest.raises(ExcelWritebackError, match="changed since staging"):
        writeback.apply(payload["store"], report.changeset,
                        approval=writeback.approve(report.changeset, "op"))
    assert load_workbook(planilla)[SHEET]["E4"].value is None  # nothing written


def test_apply_howto_deliverable_written_when_staged(planilla, tmp_path):
    report = job.run(job.prepare(str(planilla), {}))
    written = job.write_operational(report, tmp_path / "out", "Acme")
    howto = written["apply_howto"].read_text(encoding="utf-8")
    assert report.changeset.idempotency_key in howto
    assert "writeback.approve" in howto


def test_write_operational_emits_csv(planilla, tmp_path):
    report = job.run(job.prepare(str(planilla), {}))
    written = job.write_operational(report, tmp_path / "out", "Acme")
    assert written["csv"].exists()
    text = written["csv"].read_text(encoding="utf-8")
    assert "SKU-001" in text and "58" in text


def test_build_deck_writes_deliverable(planilla, tmp_path):
    report = job.run(job.prepare(str(planilla), {}))
    deck = job.build_deck(report, client="Acme", citations=("Vandeput (2020), ch. 2",))
    files = deck.write_all(tmp_path / "deck")
    assert any(p.exists() for p in files.values())
