from __future__ import annotations

import io
from typing import Tuple
import pandas as pd


REQUIRED_COLUMNS = {"merchant_id", "ts", "amount", "direction", "channel"}


def read_csv_bytes(csv_bytes: bytes, *, max_rows: int = 2_000_000) -> pd.DataFrame:
    """
    Parse CSV bytes into a DataFrame.
    Keeps only required columns + ignores extras.
    """
    df = pd.read_csv(
        io.BytesIO(csv_bytes),
        dtype=str,  # parse everything as str first; normalize later
    )
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    if len(df) > max_rows:
        raise ValueError(f"too many rows: {len(df)} > {max_rows}")

    # Keep required columns only (drop raw_* and any other extras)
    df = df[list(REQUIRED_COLUMNS)].copy()
    return df


def read_csv_bytes_with_extras(csv_bytes: bytes, *, max_rows: int = 2_000_000) -> pd.DataFrame:
    """
    Parse CSV bytes into a DataFrame including extra columns.
    Use this when you need optional fields like record_status for filtering.
    """
    df = pd.read_csv(
        io.BytesIO(csv_bytes),
        dtype=str,  # parse everything as str first; normalize later
    )
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    if len(df) > max_rows:
        raise ValueError(f"too many rows: {len(df)} > {max_rows}")

    return df
