import pandas as pd

from cashflow_ingest.ingest.adapters.csv_file import (
    REQUIRED_COLUMNS,
    read_csv_bytes,
    read_csv_bytes_with_extras,
)


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def test_read_csv_bytes_enforces_required_columns():
    csv = _csv_bytes("merchant_id,ts,amount,direction\nm1,2025-01-01T00:00:00+05:30,10,credit\n")
    try:
        read_csv_bytes(csv)
        assert False, "expected missing required columns error"
    except ValueError as e:
        assert "missing required columns" in str(e)


def test_read_csv_bytes_drops_extras():
    csv = _csv_bytes(
        "merchant_id,ts,amount,direction,channel,raw_note\n"
        "m1,2025-01-01T00:00:00+05:30,10,credit,UPI,hello\n"
    )
    df = read_csv_bytes(csv)
    assert set(df.columns) == REQUIRED_COLUMNS


def test_read_csv_bytes_with_extras_keeps_all_columns():
    csv = _csv_bytes(
        "merchant_id,ts,amount,direction,channel,record_status,partial_record\n"
        "m1,2025-01-01T00:00:00+05:30,10,credit,UPI,SUCCESS,1\n"
    )
    df = read_csv_bytes_with_extras(csv)
    assert set(REQUIRED_COLUMNS).issubset(df.columns)
    assert "record_status" in df.columns
    assert "partial_record" in df.columns
    assert isinstance(df, pd.DataFrame)
