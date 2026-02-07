from datetime import datetime, timezone

from cashflow_ingest.api.schemas import CanonicalTxn, Channel, Direction
from cashflow_ingest.ingest.pipeline.cct_aggregates import aggregate_daily_control


def _evt(ts, amount, direction, *, category=None, narration=None, payer_token=None, partial=False):
    return CanonicalTxn(
        subject_ref="s1",
        merchant_id="m1",
        event_ts=ts,
        amount=amount,
        direction=direction,
        channel=Channel.UPI,
        raw_category=category,
        raw_narration=narration,
        raw_counterparty_token=payer_token,
        partial_record=partial,
    )


def _split_amount(total: float, count: int) -> list[float]:
    base = round(total / count, 2)
    amounts = [base] * count
    # adjust last to match total exactly
    amounts[-1] = round(total - sum(amounts[:-1]), 2)
    return amounts


def test_daily_control_aggregates_example():
    day = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
    events = []

    # FREE_IN: 92, sum 68450.25
    for i, amt in enumerate(_split_amount(68450.25, 92)):
        payer = f"p{i}" if i < 61 else None  # 61 unique payers
        partial = i < 3  # 3 partial rows
        events.append(_evt(day, amt, Direction.credit, category="sale", payer_token=payer, partial=partial))

    # FREE_OUT: 1, sum 320.00
    events.append(_evt(day, 320.00, Direction.debit, category="sale"))

    # CONSTRAINED_OUT: 3, sum 42150.00
    for amt in _split_amount(42150.00, 3):
        events.append(_evt(day, amt, Direction.debit, category="rent"))

    # PASS_THROUGH_IN: 2, sum 8000.00
    for amt in _split_amount(8000.00, 2):
        events.append(_evt(day, amt, Direction.credit, narration="settlement"))

    # PASS_THROUGH_OUT: 1, sum 1200.00
    events.append(_evt(day, 1200.00, Direction.debit, narration="settlement"))

    # ARTIFICIAL_OUT: 1, sum 2500.00
    events.append(_evt(day, 2500.00, Direction.debit, narration="owner transfer"))

    # UNKNOWN_IN: 4, sum 950.00
    for amt in _split_amount(950.00, 4):
        events.append(_evt(day, amt, Direction.credit))

    daily = aggregate_daily_control(events)
    payload = daily["2026-01-15"]

    counts = payload["counts"]
    sums = payload["sums"]
    derived = payload["derived"]

    assert counts["FREE_IN"] == 92
    assert counts["FREE_OUT"] == 1
    assert counts["CONSTRAINED_OUT"] == 3
    assert counts["PASS_THROUGH_IN"] == 2
    assert counts["PASS_THROUGH_OUT"] == 1
    assert counts["ARTIFICIAL_OUT"] == 1
    assert counts["UNKNOWN_IN"] == 4

    assert sums["FREE_IN"] == 68450.25
    assert sums["FREE_OUT"] == 320.00
    assert sums["CONSTRAINED_OUT"] == 42150.00
    assert sums["PASS_THROUGH_IN"] == 8000.00
    assert sums["PASS_THROUGH_OUT"] == 1200.00
    assert sums["ARTIFICIAL_OUT"] == 2500.00
    assert sums["UNKNOWN_IN"] == 950.00

    assert derived["free_cash_net"] == 68130.25
    assert derived["unique_payers_count"] == 61
    assert derived["accepted_partial_rows"] == 3
    assert derived["unknown_cct_count"] == 4

    # Ratios (approx)
    total_in = 68450.25 + 8000.00 + 950.00
    total_out = 320.00 + 42150.00 + 1200.00 + 2500.00
    total_flow = total_in + total_out
    pass_through_ratio = (8000.00 + 1200.00) / total_flow
    unknown_flow_ratio = (950.00 + 0.00) / total_flow

    assert abs(derived["pass_through_ratio"] - round(pass_through_ratio, 6)) < 1e-6
    assert abs(derived["unknown_flow_ratio"] - round(unknown_flow_ratio, 6)) < 1e-6
