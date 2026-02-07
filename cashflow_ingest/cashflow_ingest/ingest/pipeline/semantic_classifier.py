from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cashflow_ingest.api.schemas import CanonicalTxn


@dataclass(frozen=True)
class TxnSemantic:
    subject_ref: str
    event_ts: object
    direction: str
    amount: float
    channel: str
    raw_category: str | None
    raw_narration: str | None
    raw_counterparty_token: str | None
    role_class: str
    purpose_class: str


def _text(val: str | None) -> str:
    return (val or "").strip().lower()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(k in text for k in keywords)


def classify_role_purpose(txn: CanonicalTxn) -> TxnSemantic:
    """
    Ephemeral classification using optional category/narration signals.
    Outputs role_class and purpose_class (strings).
    """
    cat = _text(txn.raw_category)
    nar = _text(txn.raw_narration)
    blob = f"{cat} {nar}".strip()

    role_class = "UNKNOWN"
    purpose_class = "UNKNOWN"

    if _contains_any(blob, ["owner", "self", "capital", "withdrawal", "infusion"]):
        role_class = "OWNER"
        purpose_class = "OWNER_TRANSFER"
    elif _contains_any(blob, ["supplier", "inventory", "stock", "procure"]):
        role_class = "SUPPLIER"
        purpose_class = "INVENTORY"
    elif _contains_any(blob, ["rent", "utility", "electricity", "water", "emi", "gst", "tax"]):
        role_class = "OBLIGATION"
        purpose_class = "OPEX_OR_STATUTORY"
    elif _contains_any(blob, ["refund", "chargeback", "reversal"]):
        role_class = "PLATFORM"
        purpose_class = "REFUND_OR_REVERSAL"
    elif _contains_any(blob, ["settlement", "gateway", "pg", "fee", "commission"]):
        role_class = "PLATFORM"
        purpose_class = "SETTLEMENT_OR_FEE"
    elif _contains_any(blob, ["sale", "sales", "invoice", "pos", "order", "revenue"]):
        role_class = "CUSTOMER"
        purpose_class = "SALE"
    elif _contains_any(blob, ["reimbursement", "insurance", "claim", "subsidy", "grant"]):
        role_class = "THIRD_PARTY"
        purpose_class = "REIMBURSEMENT"

    return TxnSemantic(
        subject_ref=txn.subject_ref,
        event_ts=txn.event_ts,
        direction=txn.direction.value if hasattr(txn.direction, "value") else str(txn.direction),
        amount=float(txn.amount),
        channel=txn.channel.value if hasattr(txn.channel, "value") else str(txn.channel),
        raw_category=txn.raw_category,
        raw_narration=txn.raw_narration,
        raw_counterparty_token=txn.raw_counterparty_token,
        role_class=role_class,
        purpose_class=purpose_class,
    )
