"""Per-call-type playbooks for the logistics voice agent (capability M16).

The 7 call types as structured data, plus a renderer that compiles one into the
numbered Goal-block steps the ElevenLabs system prompt uses (the agent's "guion").
General logistics knowledge lives in the RAG knowledge base; volatile shipment facts
arrive as dynamic variables / server-tool lookups — these playbooks are the *flow*.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CallPlaybook:
    key: str
    name: str
    goal: str
    doc_fields: tuple[str, ...]     # document fields the agent references during the call
    questions: tuple[str, ...]      # what to ask, in order
    capture: tuple[str, ...]        # what to record from the call
    escalate_when: str              # condition to hand off to a human


_PLAYBOOKS: dict[str, CallPlaybook] = {
    "eta_check": CallPlaybook(
        key="eta_check",
        name="Shipment ETA / status check",
        goal="Confirm the current ETA and surface any delay or roll.",
        doc_fields=("bl_no", "booking_no", "container_no", "vessel_voyage", "pol", "pod", "last_eta"),
        questions=(
            "Can you confirm the current ETA for this shipment?",
            "Is it still on the booked vessel, or has it been rolled?",
            "Any transshipment delay or customs hold I should know about?",
        ),
        capture=("new_eta", "status_code", "delay_reason", "next_milestone_date", "confirmed_by"),
        escalate_when="a blank-sailing or roll affects a committed delivery, or the carrier disputes the booking reference",
    ),
    "po_confirm": CallPlaybook(
        key="po_confirm",
        name="PO confirmation & expedite",
        goal="Confirm the supplier accepted the PO and a ship date; push to expedite if at risk.",
        doc_fields=("po_no", "po_date", "line_items", "requested_ship_date", "cancel_date", "incoterm"),
        questions=(
            "Did you receive purchase order {{po_no}}, and do the quantities and prices match?",
            "What ship date can you confirm?",
            "Can you pull it forward, or ship partial if needed?",
        ),
        capture=("confirmed_ship_date", "qty_price_discrepancies", "partial_ship_offer", "expedite_cost"),
        escalate_when="there is a price/quantity mismatch, the supplier refuses the ship date, or an expedite needs cost approval",
    ),
    "delivery_appointment": CallPlaybook(
        key="delivery_appointment",
        name="Reschedule / confirm delivery appointment",
        goal="Secure or move a dock appointment window.",
        doc_fields=("pro_no", "bl_no", "ship_to", "pallet_count", "requested_window", "accessorials"),
        questions=(
            "What delivery windows are available?",
            "Is it first-come-first-served or by appointment, and is a dock/liftgate available?",
            "What is the confirmation number for the booked window?",
        ),
        capture=("confirmed_window", "appointment_no", "special_equipment", "detention_risk"),
        escalate_when="no window is available before the deadline, or the facility requires terms the shipper has not authorized",
    ),
    "demurrage_check": CallPlaybook(
        key="demurrage_check",
        name="Free-time / demurrage check",
        goal="Determine the last free day and accruing charges; limit or avoid them.",
        doc_fields=("bl_no", "container_no", "last_free_day", "free_time_terms", "per_diem_rate"),
        questions=(
            "What is the last free day on this container?",
            "How many days of free time remain, and what is the current per-diem/demurrage rate?",
            "Is the container available for pickup (customs cleared), and can free time be extended?",
        ),
        capture=("last_free_day", "free_time_remaining", "daily_rate", "charges_accrued", "extension_offer"),
        escalate_when="charges are already accruing, the carrier refuses an extension, or the free-time start is disputed",
    ),
    "customs_status": CallPlaybook(
        key="customs_status",
        name="Customs / clearance status",
        goal="Confirm entry/ISF status and any holds.",
        doc_fields=("entry_no", "bl_no", "awb_no", "hts_codes", "importer_of_record", "isf_status"),
        questions=(
            "Has the entry been filed and released, and was the ISF accepted?",
            "Is there any CBP exam or hold?",
            "Are duties paid and are any documents outstanding?",
        ),
        capture=("entry_status", "exam_type", "outstanding_docs", "expected_release_date"),
        escalate_when="there is a CBP exam/hold or an ADD/CVD or classification dispute — hand to a licensed broker; never give classification or duty advice",
    ),
    "osd_intake": CallPlaybook(
        key="osd_intake",
        name="OS&D / damage dispute intake",
        goal="Gather a structured over/short/damaged report. Do NOT admit or settle liability.",
        doc_fields=("bl_no", "pro_no", "packing_list", "commercial_invoice", "pod_exceptions", "ordered_vs_received"),
        questions=(
            "Was the shipment over, short, or damaged, and which items and quantities?",
            "Was it visible at delivery or concealed, and was it noted on the POD before signing?",
            "Are photos available?",
        ),
        capture=("osd_type", "affected_skus", "damage_description", "photo_refs", "pod_exception_status", "claim_value_estimate"),
        escalate_when="always hand the liability/claim decision to a human; the agent only intakes — no liability admissions, no settlement offers",
    ),
    "pod_request": CallPlaybook(
        key="pod_request",
        name="Proof-of-delivery request",
        goal="Obtain a signed POD with delivery timestamp and any exceptions.",
        doc_fields=("bl_no", "pro_no", "ship_to", "delivery_date", "consignee_contact"),
        questions=(
            "Was the shipment delivered, and on what date and time?",
            "Who signed for it, and were any exceptions noted?",
            "Can you send the signed POD copy?",
        ),
        capture=("delivery_timestamp", "signer_name", "exception_flags", "pod_document_ref"),
        escalate_when="the POD shows exceptions or a refusal (route to OS&D intake), or the carrier cannot locate the POD",
    ),
}

PLAYBOOK_KEYS = tuple(_PLAYBOOKS.keys())


def list_playbooks() -> list[str]:
    return list(_PLAYBOOKS.keys())


def get_playbook(key: str) -> CallPlaybook:
    if key not in _PLAYBOOKS:
        raise KeyError(f"unknown call playbook: {key}")
    return _PLAYBOOKS[key]


def render_goal_block(playbook: CallPlaybook) -> str:
    """Compile a playbook into the numbered Goal-block steps for the system prompt."""
    lines = [f"# Goal — {playbook.name}", playbook.goal, "", "Steps:"]
    for i, q in enumerate(playbook.questions, start=1):
        marker = " (This step is important.)" if i == 1 else ""
        lines.append(f"{i}. Ask: {q}{marker}")
    lines.append(f"{len(playbook.questions) + 1}. Capture: {', '.join(playbook.capture)}.")
    lines.append(f"Escalate to a human when: {playbook.escalate_when}.")
    return "\n".join(lines)
