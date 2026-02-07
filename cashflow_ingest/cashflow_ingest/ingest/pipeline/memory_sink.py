from __future__ import annotations
from datetime import date
from typing import Dict, Tuple

from cashflow_ingest.ingest.pipeline.storage_port import StoragePort


class DuplicateBatchError(Exception):
    pass


class InMemorySink(StoragePort):
    """
    Development-only sink.
    NOT for production.
    """
    def __init__(self) -> None:
        self._batches = {}
        self._daily = []
        self._next_batch_id = 1

    def persist_batch(
        self,
        *,
        subject_ref: str,
        source: str,
        filename: str,
        file_hash_sha256: str,
        idempotency_key: str,
        rows_accepted: int,
        rows_rejected: int,
        range_start: date,
        range_end: date,
    ) -> int:
        if idempotency_key in self._batches:
            raise DuplicateBatchError(f"batch already ingested: {idempotency_key}")

        batch_id = self._next_batch_id
        self._next_batch_id += 1

        self._batches[idempotency_key] = {
            "batch_id": batch_id,
            "subject_ref": subject_ref,
            "source": source,
            "filename": filename,
            "rows_accepted": rows_accepted,
            "rows_rejected": rows_rejected,
            "range_start": range_start,
            "range_end": range_end,
        }
        return batch_id

    def persist_daily_aggregates(
        self,
        *,
        subject_ref: str,
        daily_aggs: Dict[date, Tuple[float, float]],
    ) -> None:
        for day, (inflow, outflow) in daily_aggs.items():
            self._daily.append({
                "subject_ref": subject_ref,
                "day": day,
                "inflow": round(inflow, 2),
                "outflow": round(outflow, 2),
            })
