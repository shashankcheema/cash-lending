from __future__ import annotations

from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, field_validator


class Direction(str, Enum):
    credit = "credit"
    debit = "debit"


class Channel(str, Enum):
    UPI = "UPI"
    CARD = "CARD"
    BANK = "BANK"
    NET_BANKING = "NET_BANKING"
    WALLET = "WALLET"
    COD_SETTLEMENT = "COD_SETTLEMENT"


class CanonicalTxn(BaseModel):
    """
    Canonical normalized transaction event.
    NOTE: In production, you persist ONLY derived aggregates, not raw txns.
    This model is for in-memory processing in ingestion.
    """
    model_config = ConfigDict(extra="ignore")

    subject_ref: str = Field(..., description="Internal merchant reference (non-PII)")
    merchant_id: str
    event_ts: datetime
    amount: float
    direction: Direction
    channel: Channel

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("amount must be > 0")
        return float(v)


class FeedEvent(BaseModel):
    """
    Event payload for JSON feeds.
    Extra fields are ignored to avoid raw-data retention.
    """
    model_config = ConfigDict(extra="ignore")

    merchant_id: object
    ts: object
    amount: object
    direction: object
    channel: object


class FeedIngestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject_ref: str = Field(..., description="Internal merchant reference (non-PII)")
    subject_ref_version: str | None = Field(None, description="Opaque alias version")
    source: str
    watermark_ts: datetime | None = Field(None, description="Upstream checkpoint for this batch")
    allow_missing_watermark: bool = False
    input_start_date: date | None = None
    input_end_date: date | None = None
    events: list[FeedEvent]
