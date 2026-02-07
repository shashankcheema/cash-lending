from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterable, Tuple

from cashflow_ingest.api.schemas import CanonicalTxn


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_batch_idempotency_key(
    *,
    subject_ref: str,
    source: str,
    file_hash_hex: str,
    min_ts: datetime,
    max_ts: datetime,
) -> str:
    """
    Stable key: subject + source + file hash + inferred date range.
    """
    payload = f"{subject_ref}|{source}|{file_hash_hex}|{min_ts.date()}|{max_ts.date()}".encode("utf-8")
    return sha256_hex(payload)


def infer_min_max_ts(events: Iterable[CanonicalTxn]) -> Tuple[datetime, datetime]:
    ts = [e.event_ts for e in events]
    return min(ts), max(ts)


def compute_feed_idempotency_key(
    *,
    subject_ref: str,
    source: str,
    watermark_ts: datetime,
    min_ts: datetime,
    max_ts: datetime,
    event_count: int,
    payload_hash_hex: str,
) -> str:
    """
    Stable key for JSON feeds:
    subject + source + watermark + range + count + payload hash.
    """
    payload = (
        f"{subject_ref}|{source}|{watermark_ts.isoformat()}|"
        f"{min_ts.isoformat()}|{max_ts.isoformat()}|{event_count}|{payload_hash_hex}"
    ).encode("utf-8")
    return sha256_hex(payload)
