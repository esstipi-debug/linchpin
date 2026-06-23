"""Logistics document field maps (capability M16, credential-free).

The 12 document types the voice agent reads, and the high-value fields to extract
from each. A shared base (shipper/consignee/notify/hs_code/weight/incoterm) recurs
across docs. The doc-reader (Claude PDF + citations) extracts to these schemas; this
module is just the structure + field map, so it needs no credentials to build/test.
Reference: research field map (BOL, invoice, packing list, PO, ASN, POD, customs,
arrival notice, freight invoice, certificate of origin, AWB, booking).
"""

from __future__ import annotations

from dataclasses import dataclass

_SHARED = ("shipper", "consignee", "notify_party", "hs_code", "gross_weight", "incoterm")


@dataclass(frozen=True)
class DocField:
    name: str
    required: bool = False
    description: str = ""


@dataclass(frozen=True)
class DocSchema:
    doc_type: str
    title: str
    fields: tuple[DocField, ...]
    notes: str = ""


def _f(spec: tuple) -> tuple[DocField, ...]:
    return tuple(DocField(*s) if isinstance(s, tuple) else DocField(s) for s in spec)


_DOC_SCHEMAS: dict[str, DocSchema] = {
    "bill_of_lading": DocSchema("bill_of_lading", "Bill of Lading (Ocean)", _f((
        ("bl_no", True), ("booking_no", False), ("container_no", True), ("seal_no", False),
        ("vessel_voyage", True), ("pol", True), ("pod", True), ("etd", False), ("eta", False),
        "freight_terms", "on_board_date", "is_negotiable", *_SHARED,
    )), notes="MBL vs HBL differ only in shipper/consignee/notify; Sea Waybill drops # originals."),
    "commercial_invoice": DocSchema("commercial_invoice", "Commercial Invoice", _f((
        ("invoice_no", True), ("invoice_date", True), "seller", "buyer", "po_ref",
        "country_of_origin", "incoterm", "currency", "line_items", "total_value",
        "freight", "insurance", "payment_terms", "hs_code",
    ))),
    "packing_list": DocSchema("packing_list", "Packing List", _f((
        ("pl_no", False), "linked_invoice", "linked_po", "carton_count", "units_per_carton",
        "total_qty", "sku_upc", "net_weight", "gross_weight", "carton_dims", "total_cbm", "pallet_ids",
    ))),
    "purchase_order": DocSchema("purchase_order", "Purchase Order", _f((
        ("po_no", True), ("po_date", True), "buyer", "supplier_id", "ship_to",
        "requested_ship_date", "cancel_date", "line_items", "currency", "incoterm",
        "payment_terms", "total_value",
    ))),
    "asn": DocSchema("asn", "Advance Shipping Notice (EDI 856)", _f((
        ("shipment_id", True), "bl_no", "carrier_scac", "ship_date", "ship_from", "ship_to",
        "po_no", "pallet_sscc", "carton_gtin", "sku_upc", "qty_shipped", "lot_serial",
    )), notes="Hierarchical: Shipment -> Order -> Tare(pallet SSCC) -> Pack(carton) -> Item."),
    "delivery_note_pod": DocSchema("delivery_note_pod", "Delivery Note / Proof of Delivery", _f((
        ("delivery_note_no", False), "delivery_datetime", "linked_order", "consignee",
        "actual_location", "qty_received_vs_ordered", "exception_notes",
        ("recipient_signature", False), "driver_carrier", "pro_no",
    ))),
    "customs_entry": DocSchema("customs_entry", "Customs Entry / CBP 7501", _f((
        ("entry_no", True), "entry_type", "importer_of_record", "ultimate_consignee",
        "port_of_entry", "country_of_origin", "bl_or_awb_no", ("hts_code", True),
        "entered_value", "duty_rate", "duty_amount", "mpf", "hmf", "add_cvd", "gross_weight",
    ))),
    "arrival_notice": DocSchema("arrival_notice", "Arrival Notice", _f((
        ("an_no", False), ("bl_no", True), "vessel_voyage", "pod", ("eta", True),
        "container_no", "seal_no", "consignee", "cargo_description", "packages",
        ("last_free_day", True), "charges_due", "release_status",
    )), notes="last_free_day is the demurrage trigger the agent must surface."),
    "freight_invoice": DocSchema("freight_invoice", "Freight Invoice (EDI 210)", _f((
        ("freight_invoice_no", True), "freight_invoice_date", "carrier_scac", "bill_to",
        "bl_or_awb_no", "pro_no", "origin", "destination", "container_size", "charge_lines",
        "chargeable_weight", "currency", "total", "freight_terms",
    ))),
    "certificate_of_origin": DocSchema("certificate_of_origin", "Certificate of Origin", _f((
        ("cert_no", False), "cert_date", "exporter", "consignee", ("country_of_origin", True),
        "goods_description", "hs_code", "qty_weight", "invoice_ref", "issuing_authority",
        "origin_criterion", "blanket_period",
    )), notes="USMCA preferential needs 9 elements; no form required."),
    "air_waybill": DocSchema("air_waybill", "Air Waybill (AWB)", _f((
        ("awb_no", True), "issuing_carrier", "shipper", "consignee", "agent",
        "origin_airport", "destination_airport", "routing", "pieces", "gross_weight",
        ("chargeable_weight", True), "rate", "total", "hs_code", "declared_value", "charge_code",
    )), notes="AWB no. = 3-digit prefix - 7-digit serial - 1 check digit. MAWB vs HAWB."),
    "booking_confirmation": DocSchema("booking_confirmation", "Booking Confirmation", _f((
        ("booking_no", True), "booking_status", "carrier_scac", "shipper", "vessel_voyage",
        "pol", "pod", "etd", "eta", ("vgm_cutoff", False), ("doc_si_cutoff", False),
        "gate_in_cutoff", "container_qty_type", "commodity", "hs_code", "freight_terms", "incoterm",
    )), notes="Cut-offs (VGM / SI / gate-in) are the time-critical fields."),
}

DOC_TYPES = tuple(_DOC_SCHEMAS.keys())


def list_doc_schemas() -> list[str]:
    return list(_DOC_SCHEMAS.keys())


def get_doc_schema(doc_type: str) -> DocSchema:
    if doc_type not in _DOC_SCHEMAS:
        raise KeyError(f"unknown document type: {doc_type}")
    return _DOC_SCHEMAS[doc_type]


def required_fields(schema: DocSchema) -> list[str]:
    return [f.name for f in schema.fields if f.required]
