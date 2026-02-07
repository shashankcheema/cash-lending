from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Iterable

from cashflow_ingest.ingest.pipeline.cct_enums import CCT
from cashflow_ingest.ingest.pipeline.semantic_classifier import TxnSemantic


@dataclass(frozen=True)
class CCTResult:
    cct: CCT
    confidence: float
    rules_fired: list[str]


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"", "none", "null"}:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _threshold_overrides() -> dict[str, float]:
    raw = os.getenv("CCT_THRESHOLDS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k).upper(): float(v) for k, v in parsed.items()}
    except Exception:
        return {}
    return {}


def _threshold_for(cct: CCT, default_min: float, overrides: dict[str, float]) -> float:
    return overrides.get(cct.value, default_min)


def _text(val: str | None) -> str:
    return (val or "").strip().lower()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(k in text for k in keywords)


def _candidates(sem: TxnSemantic) -> list[tuple[CCT, float, str]]:
    """
    Produce multiple candidates from independent evidence sources.
    """
    candidates: list[tuple[CCT, float, str]] = []

    cat = _text(sem.raw_category)
    nar = _text(sem.raw_narration)
    blob = f"{cat} {nar}".strip()

    # Hard rules (highest weight)
    if _contains_any(blob, ["settlement", "gateway", "pg", "fee", "commission"]):
        candidates.append((CCT.PASS_THROUGH, 0.90, "HARD_SETTLEMENT_FEE"))
    if _contains_any(blob, ["refund", "reversal", "chargeback"]):
        candidates.append((CCT.PASS_THROUGH, 0.88, "HARD_REFUND_REVERSAL"))
    if _contains_any(blob, ["owner", "self", "capital", "withdrawal", "infusion", "director"]):
        candidates.append((CCT.ARTIFICIAL, 0.90, "HARD_OWNER_TRANSFER"))

    # Category-based rules (medium weight)
    if _contains_any(blob, ["rent", "utility", "electricity", "water", "emi", "gst", "tax"]):
        candidates.append((CCT.CONSTRAINED, 0.75, "CAT_OBLIGATION"))
    if _contains_any(blob, ["inventory", "stock", "wholesale", "supplier", "procure"]):
        candidates.append((CCT.CONSTRAINED, 0.75, "CAT_INVENTORY"))
    if _contains_any(blob, ["sale", "sales", "invoice", "pos", "order", "revenue"]):
        candidates.append((CCT.FREE, 0.75, "CAT_SALE"))
    if _contains_any(blob, ["reimbursement", "insurance", "claim", "subsidy", "grant"]):
        candidates.append((CCT.CONDITIONAL, 0.72, "CAT_REIMBURSEMENT"))

    # Narration-based rules (medium weight)
    if _contains_any(blob, ["cashback", "promo"]):
        candidates.append((CCT.CONDITIONAL, 0.70, "NAR_CASHBACK_PROMO"))
    if _contains_any(blob, ["settle", "netting"]):
        candidates.append((CCT.PASS_THROUGH, 0.70, "NAR_SETTLEMENT"))

    # Channel + direction heuristics (low weight)
    direction = sem.direction.lower()
    channel = sem.channel.upper()
    if direction == "debit" and channel in {"NET_BANKING", "BANK"}:
        candidates.append((CCT.CONSTRAINED, 0.60, "HEUR_NETBANK_DEBIT"))
    if direction == "credit" and channel in {"UPI", "CARD", "WALLET"}:
        candidates.append((CCT.FREE, 0.60, "HEUR_CONSUMER_CREDIT"))

    # Purpose-based fallback (medium weight)
    purpose = sem.purpose_class
    if purpose == "SALE":
        candidates.append((CCT.FREE, 0.70, "PURPOSE_SALE"))
    elif purpose in {"INVENTORY", "OPEX_OR_STATUTORY"}:
        candidates.append((CCT.CONSTRAINED, 0.70, "PURPOSE_OBLIGATION"))
    elif purpose in {"SETTLEMENT_OR_FEE", "REFUND_OR_REVERSAL"}:
        candidates.append((CCT.PASS_THROUGH, 0.70, "PURPOSE_PASS_THROUGH"))
    elif purpose == "OWNER_TRANSFER":
        candidates.append((CCT.ARTIFICIAL, 0.70, "PURPOSE_OWNER_TRANSFER"))
    elif purpose == "REIMBURSEMENT":
        candidates.append((CCT.CONDITIONAL, 0.68, "PURPOSE_REIMBURSEMENT"))

    if not candidates:
        candidates.append((CCT.UNKNOWN, 0.50, "PURPOSE_UNKNOWN"))

    return candidates


def classify_cct(sem: TxnSemantic) -> CCTResult:
    """
    Apply rule candidates and resolve ambiguity.
    """
    min_conf = _env_float("MIN_CCT_CONFIDENCE", 0.70)
    ambiguity_delta = _env_float("AMBIGUITY_DELTA", 0.05)
    overrides = _threshold_overrides()

    cands = _candidates(sem)
    # pick top by confidence
    cands_sorted = sorted(cands, key=lambda x: x[1], reverse=True)
    top = cands_sorted[0]
    if len(cands_sorted) > 1:
        second = cands_sorted[1]
        if top[0] != second[0] and abs(top[1] - second[1]) <= ambiguity_delta:
            return CCTResult(cct=CCT.UNKNOWN, confidence=top[1], rules_fired=[top[2], second[2]])

    threshold = _threshold_for(top[0], min_conf, overrides)
    if threshold > 0 and top[1] < threshold:
        return CCTResult(cct=CCT.UNKNOWN, confidence=top[1], rules_fired=[top[2]])

    return CCTResult(cct=top[0], confidence=top[1], rules_fired=[top[2]])
