from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd

from cashflow_ingest.api.schemas import CanonicalTxn, Channel, Direction


_VALID_DIRECTION = {d.value for d in Direction}
_VALID_CHANNEL = {c.value for c in Channel}


def _is_missing(val: object) -> bool:
    if val is None:
        return True
    try:
        if pd.isna(val):
            return True
    except Exception:
        pass
    if isinstance(val, str) and val.strip() == "":
        return True
    return False


def normalize_df_to_events(
    df: pd.DataFrame,
    *,
    subject_ref: str,
) -> Tuple[List[CanonicalTxn], Dict[str, int], List[int]]:
    """
    Convert required-column df into CanonicalTxn objects (validated).
    Drops/ignores any extra fields by design (adapter already drops).
    """
    # Normalize ts
    # Accept ISO-like strings: "2025-11-05T19:12:22+05:30"
    df = df.copy()
    df["_ts_raw"] = df["ts"]
    df["_amount_raw"] = df["amount"]
    df["event_ts"] = pd.to_datetime(df["ts"], errors="coerce", utc=False)

    # Normalize direction lowercase
    df["direction"] = df["direction"].str.strip().str.lower()

    # Normalize channel uppercase with underscores
    df["channel"] = df["channel"].str.strip().str.upper()

    # Normalize amount
    # amount might be string "123.45"
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    events: List[CanonicalTxn] = []
    valid_indices: List[int] = []
    rejection_breakdown: Dict[str, int] = {}

    for i, row in df.iterrows():
        merchant_id = row.get("merchant_id")
        if _is_missing(merchant_id):
            rejection_breakdown["MISSING_REQUIRED_FIELD"] = rejection_breakdown.get("MISSING_REQUIRED_FIELD", 0) + 1
            continue

        ts_raw = row.get("_ts_raw")
        ts_val = row.get("event_ts")
        if _is_missing(ts_raw):
            rejection_breakdown["MISSING_REQUIRED_FIELD"] = rejection_breakdown.get("MISSING_REQUIRED_FIELD", 0) + 1
            continue
        if _is_missing(ts_val):
            rejection_breakdown["INVALID_TS"] = rejection_breakdown.get("INVALID_TS", 0) + 1
            continue

        amt_raw = row.get("_amount_raw")
        amt_val = row.get("amount")
        if _is_missing(amt_raw):
            rejection_breakdown["MISSING_REQUIRED_FIELD"] = rejection_breakdown.get("MISSING_REQUIRED_FIELD", 0) + 1
            continue
        if _is_missing(amt_val):
            rejection_breakdown["INVALID_AMOUNT"] = rejection_breakdown.get("INVALID_AMOUNT", 0) + 1
            continue
        if float(amt_val) <= 0:
            rejection_breakdown["INVALID_AMOUNT"] = rejection_breakdown.get("INVALID_AMOUNT", 0) + 1
            continue

        direction_val = row.get("direction")
        if _is_missing(direction_val):
            rejection_breakdown["MISSING_REQUIRED_FIELD"] = rejection_breakdown.get("MISSING_REQUIRED_FIELD", 0) + 1
            continue
        if direction_val not in _VALID_DIRECTION:
            rejection_breakdown["INVALID_DIRECTION"] = rejection_breakdown.get("INVALID_DIRECTION", 0) + 1
            continue

        channel_val = row.get("channel")
        if _is_missing(channel_val):
            rejection_breakdown["MISSING_REQUIRED_FIELD"] = rejection_breakdown.get("MISSING_REQUIRED_FIELD", 0) + 1
            continue
        if channel_val not in _VALID_CHANNEL:
            rejection_breakdown["INVALID_CHANNEL"] = rejection_breakdown.get("INVALID_CHANNEL", 0) + 1
            continue

        evt = CanonicalTxn(
            subject_ref=subject_ref,
            merchant_id=str(merchant_id).strip(),
            event_ts=ts_val.to_pydatetime() if pd.notna(ts_val) else None,
            amount=float(amt_val) if pd.notna(amt_val) else None,
            direction=Direction(direction_val),
            channel=Channel(channel_val),
        )
        events.append(evt)
        valid_indices.append(i)

    return events, rejection_breakdown, valid_indices
