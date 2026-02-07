from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime, time
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request

from cashflow_ingest.api.schemas import FeedIngestRequest
from cashflow_ingest.ingest.adapters.csv_file import (
    REQUIRED_COLUMNS,
    read_csv_bytes_with_extras,
)
from cashflow_ingest.ingest.pipeline.normalizer import normalize_df_to_events
from cashflow_ingest.ingest.pipeline.idempotency import (
    compute_batch_idempotency_key,
    compute_feed_idempotency_key,
    infer_min_max_ts,
)
from cashflow_ingest.ingest.pipeline.aggregates import compute_daily_inflow_outflow
from cashflow_ingest.ingest.pipeline.cct_aggregates import aggregate_daily_control
from cashflow_ingest.ingest.pipeline.memory_sink import DuplicateBatchError

router = APIRouter(prefix="/v1/ingest", tags=["ingest"])


def sha256_file_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


_REJECTION_KNOWN = {
    "FAILED_INSUFFICIENT_FUNDS",
    "FAILED_TIMEOUT",
    "FAILED_NETWORK",
    "INVALID_TOKEN",
}


def _load_min_accept_ratio() -> float | None:
    """
    MIN_ACCEPT_RATIO env:
    - unset -> default 0.10
    - empty/"0"/"none" -> disabled (returns None)
    """
    raw = os.getenv("MIN_ACCEPT_RATIO", "0.10").strip().lower()
    if raw in {"", "0", "0.0", "none", "null"}:
        return None
    try:
        return float(raw)
    except ValueError:
        # Safe default if misconfigured
        return 0.10


def _normalize_status(val: str) -> str:
    return (
        str(val)
        .strip()
        .upper()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _parse_boolish(val: object) -> bool:
    if val is None:
        return False
    if isinstance(val, float) and val != val:
        return False
    s = str(val).strip().lower()
    return s in {"1", "true", "t", "yes", "y"}


def _merge_counts(base: dict[str, int], add: dict[str, int]) -> dict[str, int]:
    for k, v in add.items():
        base[k] = base.get(k, 0) + int(v)
    return base


def _payload_hash(events: list[dict]) -> str:
    payload = json.dumps(events, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_date(val: str | None) -> date | None:
    if val is None:
        return None
    return date.fromisoformat(val)


def _range_from_declared(
    declared_start: date | None,
    declared_end: date | None,
) -> tuple[date | None, date | None]:
    if declared_start is None and declared_end is None:
        return None, None
    if declared_start is None or declared_end is None:
        raise ValueError("both input_start_date and input_end_date must be provided")
    if declared_start > declared_end:
        raise ValueError("input_start_date must be <= input_end_date")
    return declared_start, declared_end


@router.post("/files")
async def ingest_file(
    request: Request,
    subject_ref: str = Form(...),
    subject_ref_version: str | None = Form(None),
    source: str = Form(...),
    input_start_date: str | None = Form(None),
    input_end_date: str | None = Form(None),
    file: UploadFile = File(...),
):
    """
    Ingest CSV file (minimal schema) and compute derived daily aggregates in-memory.
    Persistence is via a pluggable StoragePort; current implementation is InMemorySink.
    """
    try:
        raw = await file.read()
        if not raw:
            raise ValueError("empty file")

        file_hash = sha256_file_bytes(raw)
        filename = file.filename or ""
        filename_hash = hashlib.sha256(filename.encode("utf-8")).hexdigest() if filename else ""
        file_ext = os.path.splitext(filename)[1].lower() if filename else ""

        df = read_csv_bytes_with_extras(raw)

        rows_rejected = 0
        rejection_breakdown: dict[str, int] = {}
        accepted_partial_rows = 0

        if df.empty:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "empty batch",
                    "rows_accepted": 0,
                    "rows_rejected": 0,
                    "rejection_breakdown": {},
                },
            )

        events, validation_breakdown, valid_indices = normalize_df_to_events(
            df,
            subject_ref=subject_ref,
        )
        rejection_breakdown = _merge_counts(rejection_breakdown, validation_breakdown)
        rows_rejected += sum(validation_breakdown.values())

        if len(events) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "no valid rows after filtering/validation",
                    "rows_accepted": 0,
                    "rows_rejected": rows_rejected,
                    "rejection_breakdown": rejection_breakdown,
                },
            )

        accepted_indices = list(valid_indices)
        if "record_status" in df.columns:
            status_norm = df["record_status"].map(_normalize_status)
            valid_status = status_norm.loc[valid_indices]
            accepted_mask = valid_status == "SUCCESS"

            rejected = valid_status[~accepted_mask]
            rejected_count = int(rejected.shape[0])
            rows_rejected += rejected_count

            if rejected_count:
                bucketed = rejected.where(rejected.isin(_REJECTION_KNOWN), "UNKNOWN_STATUS")
                rejection_breakdown = _merge_counts(rejection_breakdown, bucketed.value_counts().to_dict())

            accepted_indices = list(valid_status[accepted_mask].index)
            if len(accepted_indices) == 0:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "no valid rows after filtering/validation",
                        "rows_accepted": 0,
                        "rows_rejected": rows_rejected,
                        "rejection_breakdown": rejection_breakdown,
                    },
                )

            event_map = {idx: evt for idx, evt in zip(valid_indices, events)}
            events = [event_map[i] for i in accepted_indices]

        if "partial_record" in df.columns:
            partial_flags = df["partial_record"].map(_parse_boolish)
            if accepted_indices:
                accepted_partial_rows = int(partial_flags.loc[accepted_indices].sum())
            else:
                accepted_partial_rows = 0

        total_rows = len(events) + rows_rejected
        if total_rows == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "empty batch",
                    "rows_accepted": 0,
                    "rows_rejected": 0,
                    "rejection_breakdown": {},
                },
            )

        accepted_ratio = len(events) / total_rows
        min_accept_ratio = _load_min_accept_ratio()
        if min_accept_ratio is not None and accepted_ratio < min_accept_ratio:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "accepted_ratio below minimum threshold",
                    "rows_accepted": len(events),
                    "rows_rejected": rows_rejected,
                    "rejection_breakdown": rejection_breakdown,
                    "accepted_ratio": round(accepted_ratio, 4),
                    "min_accept_ratio": min_accept_ratio,
                },
            )

        min_ts, max_ts = infer_min_max_ts(events)
        declared_start = _parse_date(input_start_date)
        declared_end = _parse_date(input_end_date)
        try:
            declared_min_date, declared_max_date = _range_from_declared(declared_start, declared_end)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_declared_range",
                    "message": str(e),
                    "input_start_date": input_start_date,
                    "input_end_date": input_end_date,
                },
            )
        if declared_min_date is not None:
            if min_ts.date() < declared_min_date or max_ts.date() > declared_max_date:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "inferred range outside declared range",
                        "declared_range": {
                            "input_start_date": declared_min_date.isoformat(),
                            "input_end_date": declared_max_date.isoformat(),
                        },
                        "inferred_range": {"min_ts": min_ts.isoformat(), "max_ts": max_ts.isoformat()},
                    },
                )

        key_min_ts = declared_min_date or min_ts.date()
        key_max_ts = declared_max_date or max_ts.date()

        idem_key = compute_batch_idempotency_key(
            subject_ref=subject_ref,
            source=source,
            file_hash_hex=file_hash,
            min_ts=key_min_ts,
            max_ts=key_max_ts,
        )

        daily = compute_daily_inflow_outflow(events)
        daily_control = aggregate_daily_control(events)
        unknown_total = sum(v["derived"]["unknown_cct_count"] for v in daily_control.values()) if daily_control else 0
        total_count = sum(sum(v["counts"].values()) for v in daily_control.values()) if daily_control else 0
        cct_unknown_rate = (unknown_total / total_count) if total_count else 0.0
        payer_token_present = any(e.raw_counterparty_token for e in events)

        storage = request.app.state.storage
        try:
            batch_id = storage.persist_batch(
                subject_ref=subject_ref,
                subject_ref_version=subject_ref_version,
                source=source,
                filename_hash=filename_hash,
                file_ext=file_ext,
                file_hash_sha256=file_hash,
                idempotency_key=idem_key,
                rows_accepted=len(events),
                rows_rejected=rows_rejected,
                range_start=min_ts.date(),
                range_end=max_ts.date(),
                cct_unknown_rate=cct_unknown_rate,
            )
            storage.persist_daily_aggregates(
                subject_ref=subject_ref,
                daily_aggs=daily,
            )
            storage.persist_daily_control_aggregates(
                subject_ref=subject_ref,
                daily_control_aggs=daily_control,
            )
        except DuplicateBatchError as e:
            raise HTTPException(status_code=409, detail=str(e))

        response = {
            "status": "INGESTED_DERIVED_ONLY",
            "batch_id": batch_id,
            "subject_ref": subject_ref,
            "subject_ref_version": subject_ref_version,
            "source": source,
            "filename_hash": filename_hash,
            "file_ext": file_ext,
            "file_hash_sha256": file_hash,
            "idempotency_key": idem_key,
            "rows_accepted": len(events),
            "rows_rejected": rows_rejected,
            "rejection_breakdown": rejection_breakdown,
            "accepted_partial_rows": accepted_partial_rows,
            "range": {"min_ts": min_ts.isoformat(), "max_ts": max_ts.isoformat()},
            "inferred_range": {"min_ts": min_ts.isoformat(), "max_ts": max_ts.isoformat()},
            "daily_aggregate_days": len(daily),
            "daily_control_days": len(daily_control),
            "cct_unknown_rate": round(cct_unknown_rate, 6),
            "payer_token_present": payer_token_present,
        }
        if declared_min_date is not None:
            response["declared_range"] = {
                "input_start_date": declared_min_date.isoformat(),
                "input_end_date": declared_max_date.isoformat(),
            }
        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/feeds")
async def ingest_feed(
    request: Request,
    payload: FeedIngestRequest,
):
    """
    Ingest JSON feed events and compute derived daily aggregates.
    Uses same storage and idempotency semantics as CSV ingestion.
    """
    try:
        if payload.events is None or len(payload.events) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "empty batch",
                    "rows_accepted": 0,
                    "rows_rejected": 0,
                    "rejection_breakdown": {},
                },
            )

        watermark_ts = payload.watermark_ts
        if watermark_ts is None:
            allow_env = os.getenv("ALLOW_MISSING_WATERMARK", "").strip().lower() in {"1", "true", "yes", "y"}
            if not (payload.allow_missing_watermark and allow_env):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "missing watermark_ts",
                        "rows_accepted": 0,
                        "rows_rejected": 0,
                        "rejection_breakdown": {},
                    },
                )

        events_payload = [e.model_dump(mode="json") for e in payload.events]
        payload_hash = _payload_hash(events_payload)
        event_count = len(events_payload)

        df = pd.DataFrame(
            [
                {
                    "merchant_id": e["merchant_id"],
                    "ts": e["ts"],
                    "amount": e["amount"],
                    "direction": e["direction"],
                    "channel": e["channel"],
                    "raw_category": e.get("raw_category"),
                    "raw_narration": e.get("raw_narration"),
                    "raw_counterparty_token": e.get("raw_counterparty_token"),
                    "payer_token": e.get("payer_token"),
                    "partial_record": e.get("partial_record"),
                }
                for e in events_payload
            ]
        )

        events, validation_breakdown, _valid_indices = normalize_df_to_events(
            df,
            subject_ref=payload.subject_ref,
        )

        rows_rejected = sum(validation_breakdown.values())
        rejection_breakdown = dict(validation_breakdown)

        if len(events) == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "no valid rows after filtering/validation",
                    "rows_accepted": 0,
                    "rows_rejected": rows_rejected,
                    "rejection_breakdown": rejection_breakdown,
                },
            )

        min_ts, max_ts = infer_min_max_ts(events)
        declared_start = payload.input_start_date
        declared_end = payload.input_end_date
        try:
            declared_min_date, declared_max_date = _range_from_declared(declared_start, declared_end)
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_declared_range",
                    "message": str(e),
                    "input_start_date": declared_start.isoformat() if declared_start else None,
                    "input_end_date": declared_end.isoformat() if declared_end else None,
                },
            )
        if declared_min_date is not None:
            if min_ts.date() < declared_min_date or max_ts.date() > declared_max_date:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "inferred range outside declared range",
                        "declared_range": {
                            "input_start_date": declared_min_date.isoformat(),
                            "input_end_date": declared_max_date.isoformat(),
                        },
                        "inferred_range": {"min_ts": min_ts.isoformat(), "max_ts": max_ts.isoformat()},
                    },
                )
        effective_watermark = watermark_ts or max_ts
        key_min_ts = declared_min_date or min_ts.date()
        key_max_ts = declared_max_date or max_ts.date()

        idem_key = compute_feed_idempotency_key(
            subject_ref=payload.subject_ref,
            source=payload.source,
            watermark_ts=effective_watermark,
            min_ts=key_min_ts,
            max_ts=key_max_ts,
            event_count=event_count,
            payload_hash_hex=payload_hash,
        )

        total_rows = len(events) + rows_rejected
        if total_rows == 0:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "empty batch",
                    "rows_accepted": 0,
                    "rows_rejected": 0,
                    "rejection_breakdown": {},
                },
            )

        accepted_ratio = len(events) / total_rows
        min_accept_ratio = _load_min_accept_ratio()
        if min_accept_ratio is not None and accepted_ratio < min_accept_ratio:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "accepted_ratio below minimum threshold",
                    "rows_accepted": len(events),
                    "rows_rejected": rows_rejected,
                    "rejection_breakdown": rejection_breakdown,
                    "accepted_ratio": round(accepted_ratio, 4),
                    "min_accept_ratio": min_accept_ratio,
                },
            )

        daily = compute_daily_inflow_outflow(events)
        daily_control = aggregate_daily_control(events)
        unknown_total = sum(v["derived"]["unknown_cct_count"] for v in daily_control.values()) if daily_control else 0
        total_count = sum(sum(v["counts"].values()) for v in daily_control.values()) if daily_control else 0
        cct_unknown_rate = (unknown_total / total_count) if total_count else 0.0
        payer_token_present = any(e.raw_counterparty_token for e in events)
        storage = request.app.state.storage
        try:
            batch_id = storage.persist_batch(
                subject_ref=payload.subject_ref,
                subject_ref_version=payload.subject_ref_version,
                source=payload.source,
                filename_hash="",
                file_ext="",
                file_hash_sha256=payload_hash,
                idempotency_key=idem_key,
                rows_accepted=len(events),
                rows_rejected=rows_rejected,
                range_start=min_ts.date(),
                range_end=max_ts.date(),
                cct_unknown_rate=cct_unknown_rate,
            )
            storage.persist_daily_aggregates(
                subject_ref=payload.subject_ref,
                daily_aggs=daily,
            )
            storage.persist_daily_control_aggregates(
                subject_ref=payload.subject_ref,
                daily_control_aggs=daily_control,
            )
        except DuplicateBatchError as e:
            raise HTTPException(status_code=409, detail=str(e))

        response = {
            "status": "INGESTED_DERIVED_ONLY",
            "batch_id": batch_id,
            "subject_ref": payload.subject_ref,
            "subject_ref_version": payload.subject_ref_version,
            "source": payload.source,
            "idempotency_key": idem_key,
            "rows_accepted": len(events),
            "rows_rejected": rows_rejected,
            "rejection_breakdown": rejection_breakdown,
            "watermark_ts": effective_watermark.isoformat(),
            "range": {"min_ts": min_ts.isoformat(), "max_ts": max_ts.isoformat()},
            "inferred_range": {"min_ts": min_ts.isoformat(), "max_ts": max_ts.isoformat()},
            "daily_aggregate_days": len(daily),
            "daily_control_days": len(daily_control),
            "cct_unknown_rate": round(cct_unknown_rate, 6),
            "payer_token_present": payer_token_present,
        }
        if declared_min_date is not None:
            response["declared_range"] = {
                "input_start_date": declared_min_date.isoformat(),
                "input_end_date": declared_max_date.isoformat(),
            }
        if watermark_ts is not None and watermark_ts != effective_watermark:
            response["effective_watermark_ts"] = effective_watermark.isoformat()

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
