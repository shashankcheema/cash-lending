import pandas as pd

from cashflow_ingest.ingest.pipeline.normalizer import normalize_df_to_events


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_normalizer_valid_row():
    df = _df(
        [
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": "100.5",
                "direction": "credit",
                "channel": "UPI",
            }
        ]
    )
    events, breakdown, valid_indices = normalize_df_to_events(df, subject_ref="s1")
    assert len(events) == 1
    assert breakdown == {}
    assert valid_indices == [0]


def test_normalizer_invalid_direction():
    df = _df(
        [
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": "100.5",
                "direction": "sideways",
                "channel": "UPI",
            }
        ]
    )
    events, breakdown, valid_indices = normalize_df_to_events(df, subject_ref="s1")
    assert len(events) == 0
    assert breakdown == {"INVALID_DIRECTION": 1}
    assert valid_indices == []


def test_normalizer_missing_required_field():
    df = _df(
        [
            {
                "merchant_id": "",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": "10",
                "direction": "credit",
                "channel": "UPI",
            }
        ]
    )
    events, breakdown, valid_indices = normalize_df_to_events(df, subject_ref="s1")
    assert len(events) == 0
    assert breakdown == {"MISSING_REQUIRED_FIELD": 1}
    assert valid_indices == []


def test_normalizer_invalid_ts():
    df = _df(
        [
            {
                "merchant_id": "m1",
                "ts": "not-a-date",
                "amount": "10",
                "direction": "credit",
                "channel": "UPI",
            }
        ]
    )
    events, breakdown, valid_indices = normalize_df_to_events(df, subject_ref="s1")
    assert len(events) == 0
    assert breakdown == {"INVALID_TS": 1}
    assert valid_indices == []


def test_normalizer_invalid_amount():
    df = _df(
        [
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": "-5",
                "direction": "credit",
                "channel": "UPI",
            }
        ]
    )
    events, breakdown, valid_indices = normalize_df_to_events(df, subject_ref="s1")
    assert len(events) == 0
    assert breakdown == {"INVALID_AMOUNT": 1}
    assert valid_indices == []
