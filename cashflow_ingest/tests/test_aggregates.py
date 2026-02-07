from datetime import datetime, timezone

from cashflow_ingest.ingest.pipeline.aggregates import compute_daily_inflow_outflow
from cashflow_ingest.api.schemas import CanonicalTxn, Channel, Direction


def _evt(ts: datetime, amount: float, direction: Direction) -> CanonicalTxn:
    return CanonicalTxn(
        subject_ref="s1",
        merchant_id="m1",
        event_ts=ts,
        amount=amount,
        direction=direction,
        channel=Channel.UPI,
    )


def test_daily_aggregates():
    t1 = datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    t3 = datetime(2025, 1, 2, 9, 0, tzinfo=timezone.utc)
    events = [
        _evt(t1, 100.0, Direction.credit),
        _evt(t2, 50.0, Direction.debit),
        _evt(t3, 20.0, Direction.credit),
    ]
    daily = compute_daily_inflow_outflow(events)
    assert daily[t1.date()] == (100.0, 50.0)
    assert daily[t3.date()] == (20.0, 0.0)
