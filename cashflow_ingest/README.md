# cashflow_ingest

Regulatory-safe ingestion boundary for MSME cash-flow data. Accepts CSV uploads, validates and normalizes in-memory, computes derived daily aggregates, and persists only derived outputs via a pluggable storage interface. Raw transactions, statements, narrations, and counterparty identifiers are never stored.

## Purpose
This service is part of a larger lending / cash-flow intelligence platform. It provides a clean, deterministic ingestion boundary that is compliant with strict data minimization rules while staying extensible for future feeds (AA / UPI / bank).

## Non-Negotiable Constraints
- No raw transaction data at rest.
- No statements, narrations, UPI IDs, account numbers, or counterparty identifiers.
- Derived-only persistence.
- Idempotent ingestion: same input must generate the same idempotency key and be rejected on re-upload.
- Pluggable persistence via an interface (current implementation is in-memory).

## What’s Implemented
- FastAPI app with `/health`.
- `POST /v1/ingest/files` for CSV uploads.
- `POST /v1/ingest/feeds` for JSON feed ingestion.
- CSV parsing with required-column enforcement and extra-column drops.
- Canonical in-memory normalization with row-level validation.
- Deterministic idempotency key generation.
- Derived daily inflow/outflow aggregation.
- In-memory persistence via `StoragePort`.
- Duplicate batch detection (`409 Conflict`).
- Paytm-like support with optional `record_status` filtering (only `SUCCESS` rows).
- Row-level rejection counts by reason (counts only).
- Optional `partial_record` quality flag with `accepted_partial_rows`.

## API

### `GET /health`
Response:
```json
{ "ok": true }
```

### `POST /v1/ingest/files`
Multipart form fields:
- `subject_ref` (string): internal non-PII merchant reference.
- `source` (string): e.g., `PAYTM`, `BANK`.
- `file` (CSV).

Required CSV columns:
- `merchant_id`
- `ts`
- `amount`
- `direction`
- `channel`

Extras are dropped by design.
Optional columns (Paytm-like):
- `record_status` (if present: only `SUCCESS` rows are processed)
- `partial_record` (quality flag; accepted if otherwise valid)

Response includes:
- `batch_id`, `idempotency_key`, file hash
- `rows_accepted`, `rows_rejected`, `rejection_breakdown`, `accepted_partial_rows`
- inferred date range
- number of aggregate days

Example:
```bash
curl -X POST http://localhost:8000/v1/ingest/files \
  -F "subject_ref=mrc_001" \
  -F "source=PAYTM" \
  -F "file=@/path/to/transactions.csv"
```

### `POST /v1/ingest/feeds`
JSON body:
- `subject_ref` (string): internal non-PII merchant reference.
- `source` (string): e.g., `PAYTM`, `BANK`.
- `watermark_ts` (datetime, required): upstream checkpoint for this batch.
- `allow_missing_watermark` (bool, optional; dev-only with env gate).
- `events` (array of objects):
  - `merchant_id`, `ts`, `amount`, `direction`, `channel`

Response includes:
- `batch_id`, `idempotency_key`
- `rows_accepted`, `rows_rejected`, `rejection_breakdown`
- `watermark_ts`
- inferred date range
- number of aggregate days

Example:
```bash
curl -X POST http://localhost:8000/v1/ingest/feeds \
  -H "Content-Type: application/json" \
  -d '{
    "subject_ref": "mrc_001",
    "source": "PAYTM",
    "watermark_ts": "2025-11-06T00:00:00+05:30",
    "events": [
      {
        "merchant_id": "MRC-001",
        "ts": "2025-11-05T09:01:00+05:30",
        "amount": 120.5,
        "direction": "credit",
        "channel": "UPI"
      },
      {
        "merchant_id": "MRC-001",
        "ts": "2025-11-05T12:45:10+05:30",
        "amount": 80.0,
        "direction": "debit",
        "channel": "BANK"
      }
    ]
  }'
```

## Processing Pipeline (Current)
1. Read file bytes and compute `sha256`.
2. Parse CSV → DataFrame.
3. Enforce required columns.
4. Validate required fields + canonical values; count row-level rejects.
5. If `record_status` exists: keep only `SUCCESS` rows; count rejects by reason.
6. Track accepted rows with `partial_record=true` as a quality metric.
7. Normalize to `CanonicalTxn` (in-memory only).
8. Infer `min_ts`/`max_ts`.
9. Compute deterministic idempotency key.
10. Aggregate daily inflow/outflow totals.
11. Persist batch metadata + daily aggregates via `StoragePort`.

Feeds follow the same pipeline with JSON parsing and a feed-specific idempotency key:
`sha256(subject_ref|source|watermark|min_ts|max_ts|event_count|payload_hash)`.

## Canonical Transaction Model (In-Memory Only)
```
CanonicalTxn:
  subject_ref: str
  merchant_id: str
  event_ts: datetime
  amount: float
  direction: credit | debit
  channel: UPI | CARD | BANK | NET_BANKING | WALLET | COD_SETTLEMENT
```
These objects are never persisted.

## Idempotency
Idempotency key:
```
sha256(subject_ref + source + file_hash + min_date + max_date)
```
Re-ingesting the same file deterministically returns `409 Conflict`.

## Configuration
- `MIN_ACCEPT_RATIO` (default `0.10`): minimum accepted/total ratio.
- Set `MIN_ACCEPT_RATIO` to `0`, `0.0`, empty, `none`, or `null` to disable.
- Always fails with `400` if `rows_accepted == 0`.
- `ALLOW_MISSING_WATERMARK` (default disabled): only when set to `1/true/yes/y`
  can `allow_missing_watermark=true` be honored for feeds (dev-only).

## Repository Structure
```
cashflow_ingest/
  api/
    app.py            # FastAPI app + dependency wiring
    routes_ingest.py  # /v1/ingest/files endpoint
    schemas.py        # CanonicalTxn + enums

  ingest/
    adapters/
      csv_file.py     # CSV parsing, required-column enforcement

    pipeline/
      normalizer.py   # Raw → CanonicalTxn normalization
      idempotency.py  # Deterministic batch key computation
      aggregates.py   # Derived-only daily aggregates
      storage_port.py # Persistence interface (port)
      memory_sink.py  # In-memory implementation (adapter)

  ops/                # Empty for now
  store/              # DB implementation deferred
```

## Data Packs
`data/` contains synthetic pharmacy CSVs for testing:
- Minimal RBI-safe schema files.
- Paytm-like files with extra ephemeral columns; ingestion must drop them.

## What Is Explicitly Not Implemented Yet
- Postgres persistence.
- Feed ingestion (JSON events).
- Observability / metrics / auth / rate limiting.

## Immediate Next Safe Improvements (Ideas)
- Request size limits and structured logging (no raw payloads).
- Add `PostgresSink` implementing `StoragePort` without breaking `InMemorySink`.
