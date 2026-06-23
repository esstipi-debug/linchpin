"""Tests for the Inventory vs SCM operating-mode split."""
from __future__ import annotations

from scm_agent.modes import (
    INVENTORY,
    MODES,
    SCM,
    build_registry,
    get_mode,
    orchestrator_for,
)
from scm_agent.tools import build_default_registry


def test_scm_mode_exposes_every_tool():
    full = build_default_registry()
    scm_reg = build_registry(SCM, full)
    assert {t.key for t in scm_reg.list()} == {t.key for t in full.list()}


def test_inventory_mode_excludes_leadership():
    keys = {t.key for t in build_registry(INVENTORY).list()}
    assert "inventory_optimization" in keys
    assert "leadership_chain" not in keys


def test_inventory_is_strict_subset_of_scm():
    inv = {t.key for t in build_registry(INVENTORY).list()}
    scm = {t.key for t in build_registry(SCM).list()}
    assert inv and inv < scm


def test_get_mode_resolves_and_defaults_to_superset():
    assert get_mode("inventory") is INVENTORY
    assert get_mode("SCM") is SCM           # case-insensitive
    assert get_mode(None) is SCM            # empty -> superset
    assert get_mode("nonsense") is SCM      # unknown -> safe superset


def test_includes_helper_and_future_tools():
    assert INVENTORY.includes("inventory_optimization")
    assert not INVENTORY.includes("leadership_chain")
    assert SCM.includes("leadership_chain")
    assert SCM.includes("some_future_tool")  # superset admits tools added later
    assert not INVENTORY.includes("some_future_tool")  # inventory stays narrow


def test_modes_have_distinct_personas_and_catalogues():
    assert INVENTORY.persona != SCM.persona
    assert INVENTORY.deliverables and INVENTORY.kpis
    assert SCM.deliverables and SCM.kpis
    assert len(SCM.deliverables) > len(INVENTORY.deliverables)
    assert set(MODES) == {"inventory", "scm"}


def test_orchestrator_for_mode_is_scoped():
    orch = orchestrator_for(INVENTORY)
    keys = {t.key for t in orch.registry.list()}
    assert "leadership_chain" not in keys
    assert "inventory_optimization" in keys
