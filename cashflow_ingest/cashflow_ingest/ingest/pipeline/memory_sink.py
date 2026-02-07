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
        subject_ref_version: str | None,
        source: str,
        filename_hash: str,
        file_ext: str,
        file_hash_sha256: str,
        idempotency_key: str,
        rows_accepted: int,
        rows_rejected: int,
        range_start: date,
        range_end: date,
        cct_unknown_rate: float,
    ) -> int:
        if idempotency_key in self._batches:
            raise DuplicateBatchError(f"batch already ingested: {idempotency_key}")

        batch_id = self._next_batch_id
        self._next_batch_id += 1

        self._batches[idempotency_key] = {
            "batch_id": batch_id,
            "subject_ref": subject_ref,
            "subject_ref_version": subject_ref_version,
            "source": source,
            "filename_hash": filename_hash,
            "file_ext": file_ext,
            "rows_accepted": rows_accepted,
            "rows_rejected": rows_rejected,
            "range_start": range_start,
            "range_end": range_end,
            "cct_unknown_rate": round(float(cct_unknown_rate), 6),
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

    def persist_daily_control_aggregates(
        self,
        *,
        subject_ref: str,
        daily_control_aggs: Dict[str, dict],
    ) -> None:
        for day, payload in daily_control_aggs.items():
            self._daily.append({
                "subject_ref": subject_ref,
                "day": day,
                "control": payload,
            })
