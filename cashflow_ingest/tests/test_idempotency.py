from datetime import datetime, timezone

from cashflow_ingest.ingest.pipeline.idempotency import (
    compute_batch_idempotency_key,
    compute_feed_idempotency_key,
    infer_min_max_ts,
)
from cashflow_ingest.api.schemas import CanonicalTxn, Channel, Direction


def _evt(ts: datetime) -> CanonicalTxn:
    return CanonicalTxn(
        subject_ref="s1",
        merchant_id="m1",
        event_ts=ts,
        amount=10.0,
        direction=Direction.credit,
        channel=Channel.UPI,
    )


def test_infer_min_max_ts():
    t1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2025, 1, 3, tzinfo=timezone.utc)
    t3 = datetime(2025, 1, 2, tzinfo=timezone.utc)
    min_ts, max_ts = infer_min_max_ts([_evt(t1), _evt(t2), _evt(t3)])
    assert min_ts == t1
    assert max_ts == t2


def test_idempotency_key_stable():
    key1 = compute_batch_idempotency_key(
        subject_ref="s1",
        source="PAYTM",
        file_hash_hex="abc",
        min_ts=datetime(2025, 1, 1),
        max_ts=datetime(2025, 1, 2),
    )
    key2 = compute_batch_idempotency_key(
        subject_ref="s1",
        source="PAYTM",
        file_hash_hex="abc",
        min_ts=datetime(2025, 1, 1),
        max_ts=datetime(2025, 1, 2),
    )
    assert key1 == key2


def test_feed_idempotency_key_stable():
    key1 = compute_feed_idempotency_key(
        subject_ref="s1",
        source="PAYTM",
        watermark_ts=datetime(2025, 1, 1),
        min_ts=datetime(2025, 1, 1),
        max_ts=datetime(2025, 1, 2),
        event_count=3,
        payload_hash_hex="deadbeef",
    )
    key2 = compute_feed_idempotency_key(
        subject_ref="s1",
        source="PAYTM",
        watermark_ts=datetime(2025, 1, 1),
        min_ts=datetime(2025, 1, 1),
        max_ts=datetime(2025, 1, 2),
        event_count=3,
        payload_hash_hex="deadbeef",
    )
    assert key1 == key2
