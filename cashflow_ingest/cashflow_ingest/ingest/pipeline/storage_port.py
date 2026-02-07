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
        """Returns batch_id"""

    @abstractmethod
    def persist_daily_aggregates(
        self,
        *,
        subject_ref: str,
        daily_aggs: Dict[date, Tuple[float, float]],
    ) -> None:
        """daily_aggs: day -> (inflow, outflow)"""

    @abstractmethod
    def persist_daily_control_aggregates(
        self,
        *,
        subject_ref: str,
        daily_control_aggs: Dict[str, dict],
    ) -> None:
        """daily_control_aggs: day -> control-bucket aggregates"""
