from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date
from typing import Dict, Tuple


class StoragePort(ABC):
    @abstractmethod
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
        """Returns batch_id"""

    @abstractmethod
    def persist_daily_aggregates(
        self,
        *,
        subject_ref: str,
        daily_aggs: Dict[date, Tuple[float, float]],
    ) -> None:
        """daily_aggs: day -> (inflow, outflow)"""

