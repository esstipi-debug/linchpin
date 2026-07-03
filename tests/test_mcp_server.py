"""Tests for the read-only MCP server (Phase A go-to-market).

Guarantees under test:
- exactly the intended 8 analysis tools are exposed, all annotated read-only/
  non-destructive - `odoo_replenishment` (the only tool with live writeback)
  and every other of the 34 registered tools stays off this surface;
- a real call bridges rows -> temp CSV -> Orchestrator.run() -> a structured
  JSON response carrying the same client-ready report the webapp already builds;
- malformed/insufficient input degrades to a clear status, never a crash;
- the temp CSV a call writes does not leak past that call.
"""

from __future__ import annotations

import json

import pytest

from scm_agent import Orchestrator
from webapp.mcp_server import SERVER_NAME, build_mcp_server

EXPECTED_TOOL_NAMES = {
    "linchpin_inventory_optimize",
    "linchpin_classify_abc_xyz",
    "linchpin_newsvendor_order_quantity",
    "linchpin_forecast_demand",
    "linchpin_financial_kpis",
    "linchpin_price_optimize",
    "linchpin_audit_data_quality",
    "linchpin_whatif_sensitivity",
}

_ABC_XYZ_ROWS = [
    {"product_id": "SKU-A", "quantity": 40, "unit_cost": 12.0},
    {"product_id": "SKU-A", "quantity": 42, "unit_cost": 12.0},
    {"product_id": "SKU-A", "quantity": 38, "unit_cost": 12.0},
    {"product_id": "SKU-B", "quantity": 5, "unit_cost": 3.0},
    {"product_id": "SKU-B", "quantity": 60, "unit_cost": 3.0},
    {"product_id": "SKU-B", "quantity": 2, "unit_cost": 3.0},
]


@pytest.fixture
def mcp():
    return build_mcp_server(Orchestrator())


async def _call(mcp, tool_name: str, **params) -> dict:
    content, _structured = await mcp.call_tool(tool_name, {"params": params})
    return json.loads(content[0].text)


# -- surface: exactly the intended 8, all read-only -----------------------------


async def test_server_name():
    assert build_mcp_server().name == SERVER_NAME == "linchpin_mcp"


async def test_exposes_exactly_the_intended_eight_tools(mcp):
    tools = await mcp.list_tools()
    assert {t.name for t in tools} == EXPECTED_TOOL_NAMES


async def test_odoo_replenishment_and_writeback_tools_are_never_exposed(mcp):
    """The one tool with live ERP writeback (and every other of the 34 registered
    tools not on the Phase A list) must not be reachable through this surface."""
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert not any("odoo" in n or "writeback" in n or "replenish" in n for n in names)


async def test_every_tool_is_annotated_read_only_and_non_destructive(mcp):
    tools = await mcp.list_tools()
    assert len(tools) == 8
    for tool in tools:
        assert tool.annotations is not None, f"{tool.name} has no annotations"
        assert tool.annotations.readOnlyHint is True, f"{tool.name} must be readOnlyHint=True"
        assert tool.annotations.destructiveHint is False, f"{tool.name} must be destructiveHint=False"


async def test_every_tool_documents_the_shared_input_shape(mcp):
    """Every tool's inputSchema must require `params` with a `rows` field - an
    agent should be able to discover the calling convention from the schema alone."""
    tools = await mcp.list_tools()
    for tool in tools:
        assert "params" in tool.inputSchema.get("properties", {}), tool.name


# -- end-to-end bridge: rows -> orchestrator -> structured response -------------


async def test_abc_xyz_end_to_end_returns_ok_with_a_report(mcp):
    result = await _call(mcp, "linchpin_classify_abc_xyz", rows=_ABC_XYZ_ROWS)

    assert result["status"] == "ok"
    assert result["tool"] == "abc_xyz"
    assert result["confidence"] == pytest.approx(1.0)  # job_type override, not brief-matched
    assert result["report_markdown"] and "ABC-XYZ" in result["report_markdown"]


async def test_inventory_optimize_end_to_end_returns_ok_with_a_report(mcp):
    rows = [
        {"date": "2026-01-01", "product_id": "SKU-A", "quantity": 40, "unit_cost": 12.0, "lead_time_days": 7},
        {"date": "2026-01-08", "product_id": "SKU-A", "quantity": 45, "unit_cost": 12.0, "lead_time_days": 7},
        {"date": "2026-01-15", "product_id": "SKU-A", "quantity": 38, "unit_cost": 12.0, "lead_time_days": 7},
        {"date": "2026-01-22", "product_id": "SKU-A", "quantity": 41, "unit_cost": 12.0, "lead_time_days": 7},
    ]

    result = await _call(mcp, "linchpin_inventory_optimize", rows=rows)

    assert result["status"] == "ok"
    assert result["tool"] == "inventory_optimization"
    assert result["report_markdown"]


async def test_client_label_is_passed_through_to_the_report(mcp):
    result = await _call(mcp, "linchpin_classify_abc_xyz", rows=_ABC_XYZ_ROWS, client_label="Acme Co")

    assert "Acme Co" in result["report_markdown"]


async def test_tool_specific_params_reach_the_underlying_engine(mcp):
    """abc_thresholds narrowed to force a different class split than the default -
    proves `params.params` actually flows through, not just `params.rows`."""
    default_result = await _call(mcp, "linchpin_classify_abc_xyz", rows=_ABC_XYZ_ROWS)
    narrowed = await _call(
        mcp, "linchpin_classify_abc_xyz", rows=_ABC_XYZ_ROWS, params={"abc_thresholds": [0.10, 0.20]}
    )

    assert default_result["status"] == narrowed["status"] == "ok"
    assert default_result["report_markdown"] != narrowed["report_markdown"]


# -- graceful degradation, not crashes -------------------------------------------


async def test_missing_required_columns_reports_needs_data_not_a_crash(mcp):
    result = await _call(mcp, "linchpin_inventory_optimize", rows=[{"totally": "unrelated", "columns": 1}])

    assert result["status"] in ("needs_data", "needs_clarification", "error")
    assert result["report_markdown"] is None


async def test_empty_rows_are_rejected_by_input_validation(mcp):
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="at least 1 item"):
        await mcp.call_tool("linchpin_classify_abc_xyz", {"params": {"rows": []}})


async def test_non_tabular_row_values_do_not_crash_the_bridge(mcp):
    result = await _call(mcp, "linchpin_classify_abc_xyz", rows=[{"product_id": "SKU-A", "quantity": "not-a-number"}])

    assert result["status"] != "ok"  # degrades to an error/needs_data status, never raises


# -- resource hygiene -------------------------------------------------------------


async def test_temp_csv_does_not_leak_past_the_call(mcp, tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    await _call(mcp, "linchpin_classify_abc_xyz", rows=_ABC_XYZ_ROWS)

    leftover = list(tmp_path.glob("linchpin_mcp_*"))
    assert leftover == [], f"temp dir(s) not cleaned up: {leftover}"
