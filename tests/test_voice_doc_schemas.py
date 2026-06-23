"""Tests for the logistics document field maps (capability M16, credential-free)."""

import pytest

from src.voice.doc_schemas import (
    DOC_TYPES,
    DocSchema,
    get_doc_schema,
    list_doc_schemas,
    required_fields,
)


def test_twelve_document_types():
    keys = list_doc_schemas()
    assert len(keys) == 12
    assert set(keys) == set(DOC_TYPES)


def test_bill_of_lading_key_fields():
    s = get_doc_schema("bill_of_lading")
    assert isinstance(s, DocSchema)
    names = {f.name for f in s.fields}
    assert {"bl_no", "container_no", "vessel_voyage", "pol", "pod"} <= names


def test_arrival_notice_has_last_free_day():
    names = {f.name for f in get_doc_schema("arrival_notice").fields}
    assert "last_free_day" in names  # the demurrage trigger


def test_commercial_invoice_has_hs_and_incoterm():
    names = {f.name for f in get_doc_schema("commercial_invoice").fields}
    assert "hs_code" in names and "incoterm" in names


def test_required_fields_subset():
    s = get_doc_schema("purchase_order")
    req = required_fields(s)
    allf = {f.name for f in s.fields}
    assert set(req) <= allf
    assert "po_no" in req


def test_unknown_doc_type_raises():
    with pytest.raises(KeyError):
        get_doc_schema("napkin")
