# Cashflow Ingestion Backend — Current State & Capabilities

**Document Purpose**
This document is a living technical snapshot of what has been implemented so far in the `cashflow_ingest` backend service.

It is designed so that:
- A code-generation model (Codex) can quickly identify modules, interfaces, and responsibilities.
- An agent / reasoning model can understand why things were built this way, including regulatory constraints and future extension points.

This is not a roadmap. It is a factual description of the current working system.

---

**High-Level Goal of the Service**
`cashflow_ingest` is a regulatory-safe ingestion service for MSME cash-flow analysis.

Responsibilities NOT included:
- Store raw transaction data.
- Store merchant / customer / counterparty identifiers.
- Perform credit decisions.

Responsibilities included:
- Ingest transaction files and feeds.
- Validate and normalize data.
- Compute derived-only aggregates.
- Classify CCT and compute daily control-bucket aggregates.
- Enforce idempotent batch ingestion.
- Prepare clean inputs for downstream analytics (DP, CCT, EWS, scoring).

---

**Key Design Constraints (Non-Negotiable)**
These constraints shape every implementation decision:

1. No raw transaction data at rest.
2. Derived-only persistence.
3. Idempotent ingestion.
4. Pluggable storage.
5. Future-ready feeds (AA / UPI / GST / bank) without redesign.

---

**Technology Stack (Current)**
- Language: Python 3
- Dependency management: Poetry
- API framework: FastAPI
- Validation: Pydantic v2
- Parsing: pandas (CSV adapter)
- Persistence: In-memory sink (temporary, dev-only)

Postgres / Docker intentionally deferred.

---

**Repository Structure (Implemented)**
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
      semantic_classifier.py # Role or purpose classification
      cct_classifier.py      # CCT classification + confidence
      cct_aggregates.py      # Control-bucket aggregates
      cct_enums.py           # CCT enum
      idempotency.py  # Deterministic batch key computation
      aggregates.py   # Derived-only daily aggregates
      storage_port.py # Persistence interface (port)
      memory_sink.py  # In-memory implementation (adapter)

  ops/                # Empty for now
  store/              # DB implementation deferred
```

---

**Implemented API Endpoints**

`GET /health`
- Purpose: Liveness check.
- Response:
```json
{ "ok": true }
```

`POST /v1/ingest/files`
- Purpose:
- Ingest CSV files containing transaction records.
- Compute derived aggregates.
- Classify CCT and compute daily control-bucket aggregates.
- Enforce idempotency.
- Filter failures when `record_status` exists.
- Track row-level rejection counts (counts only).
- Track accepted partial rows via `partial_record` quality flag.
- Guardrail on garbage batches via `MIN_ACCEPT_RATIO` (default 10%).
- Support declared range inputs (`input_start_date`, `input_end_date`) with validation.
- Accept `subject_ref_version` for aliasing (does not affect idempotency).

Request (multipart form):
- `subject_ref` (string): internal merchant identifier (non-PII).
- `subject_ref_version` (string, optional): alias version for re-keying.
- `source` (string): e.g. `PAYTM`, `BANK`.
- `file` (CSV).
- `input_start_date` (YYYY-MM-DD, optional)
- `input_end_date` (YYYY-MM-DD, optional)

Response includes:
- `filename_hash`, `file_ext` (raw filename not returned)
- `declared_range` (if provided), `inferred_range` (always)
- `daily_control_days`, `cct_unknown_rate`, `payer_token_present`

Required CSV columns:
- `merchant_id`
- `ts`
- `amount`
- `direction`
- `channel`

Only required and optional columns are read; other extras are dropped. This allows:
- Minimal RBI-safe files.
- Paytm-like files with extra columns (extras ignored).
Optional columns (Paytm-like):
- `record_status` (if present: only `SUCCESS` rows are processed)
- `partial_record` (quality flag; accepted if otherwise valid)
- `raw_category` (ephemeral, optional)
- `raw_narration` (ephemeral, optional)
- `raw_counterparty_token` (ephemeral, optional)
- `payer_token` (ephemeral, optional; preferred)

`POST /v1/ingest/feeds`
- Purpose:
- Ingest JSON feed events containing the same canonical fields.
- Compute derived aggregates.
- Enforce idempotency with watermark-based key.
- Guardrail on garbage batches via `MIN_ACCEPT_RATIO`.
- Replay protection on idempotency key.
- Support declared range inputs (`input_start_date`, `input_end_date`) with validation.
- Accept `subject_ref_version` for aliasing (does not affect idempotency).

Request (JSON):
- `subject_ref`, `subject_ref_version`, `source`, `watermark_ts`, `events[]`
- `input_start_date`, `input_end_date` (optional)

Required event fields:
- `merchant_id`
- `ts`
- `amount`
- `direction`
- `channel`

---

**Processing Pipeline (In-Memory)**
1. Read file bytes.
2. Compute `file_hash_sha256`.
3. Parse CSV → DataFrame.
4. Enforce required columns.
5. Validate required fields + canonical values; count row-level rejects.
6. If `record_status` exists: keep only `SUCCESS` rows; count rejects by reason.
7. Track accepted rows with `partial_record=true` as a quality metric.
8. Normalize to `CanonicalTxn`.
9. Infer date range (`min_ts`, `max_ts`).
10. If declared range provided: validate inferred range within declared range.
11. Compute deterministic idempotency key (uses declared range if provided).
11. Compute derived daily aggregates.
12. Persist via storage port.

Feeds pipeline is equivalent, with JSON parsing and idempotency key:
`sha256(subject_ref|source|watermark|min_ts|max_ts|event_count|payload_hash)`.

Filename handling:
- Raw filenames are not persisted.
- Stored values: `filename_hash` and `file_ext`.

---

**Canonical Transaction Model (In-Memory Only)**
```
CanonicalTxn:
  subject_ref: str
  merchant_id: str
  event_ts: datetime
  amount: float
  direction: credit | debit
  channel: UPI | CARD | BANK | NET_BANKING | WALLET | COD_SETTLEMENT
```

Important:
- These objects are never persisted.
- They exist only inside the ingestion request lifecycle.

---

**Idempotency Strategy (Implemented)**
Idempotency key:
```
sha256(
  subject_ref +
  source +
  file_hash +
  inferred_date_range
)
```

Behavior:
- First ingestion: accepted.
- Same file uploaded again: HTTP 409 Conflict.

---

**What Is Explicitly NOT Implemented Yet**
This is important context for any agent reading this:
- No database (Postgres deferred).
- No feed ingestion (JSON events).
- No Cash Control (CCT) classification yet.
- No observability / metrics.
- No auth / rate limiting.

---

**Why This State Is Valuable**
At this point, the backend already provides:
- A regulatory-aligned ingestion boundary.
- A clean contract for downstream analytics.
- A testable, deterministic pipeline.
- A safe foundation for adding:
- Paytm-like negative cases.
- AA / UPI feeds.
- CCT / DP / EWS logic.
- Postgres persistence.
- No architectural rework is required.

---

**Immediate Next Logical Steps (Not Yet Implemented)**
- Replace in-memory sink with Postgres sink.
- Add Cash Control (CCT) aggregation layer.
- Add batch status API.
