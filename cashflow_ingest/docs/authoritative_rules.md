# Authoritative Rules — cashflow_ingest

This document is the single source of truth for rules, conditions, and enforcement logic in the `cashflow_ingest` backend. It is written for backend engineers, data scientists, risk/compliance reviewers, and future AI agents. It describes what rules exist, why they exist, and how they are enforced.

Service name: `cashflow_ingest`  
Purpose: Regulatory-safe ingestion boundary for MSME cash-flow data. It converts raw inputs into derived-only aggregates and enforces compliance by design. The service must never persist raw transaction data, counterparty identifiers, narrations, or payer information.

---

**1) Input & Schema Rules**

**Required fields (file ingestion)**
- Multipart fields: `subject_ref`, `source`, `file`.
- CSV required columns: `merchant_id`, `ts`, `amount`, `direction`, `channel`.

**Optional fields (file ingestion)**
- `subject_ref_version`: alias version for re-keying (does not affect idempotency).
- `input_start_date`, `input_end_date` (YYYY-MM-DD): declared range.
- Optional CSV columns (ephemeral-only): `record_status`, `partial_record`, `raw_category`, `raw_narration`, `raw_counterparty_token`, `payer_token`.

**Required fields (feed ingestion)**
- JSON body: `subject_ref`, `source`, `watermark_ts`, `events[]`.
- Each event requires: `merchant_id`, `ts`, `amount`, `direction`, `channel`.

**Optional fields (feed ingestion)**
- `subject_ref_version`: alias version for re-keying (does not affect idempotency).
- `allow_missing_watermark` (dev-only override; requires env gate).
- `input_start_date`, `input_end_date` (YYYY-MM-DD): declared range.
- Optional event fields (ephemeral-only): `raw_category`, `raw_narration`, `raw_counterparty_token`, `payer_token`, `partial_record`.

**Accepted enums**
- Direction: `credit`, `debit`.
- Channel: `UPI`, `CARD`, `BANK`, `NET_BANKING`, `WALLET`, `COD_SETTLEMENT`.

**Timestamp validation**
- `ts` must be parseable to datetime. Invalid timestamps are rejected per-row.

**Amount validation**
- Must parse to numeric and be `> 0`. Invalid or non-positive amounts are rejected per-row.

**Missing or malformed fields**
- Missing required fields → per-row rejection under `MISSING_REQUIRED_FIELD`.
- Invalid `direction`, `channel`, `ts`, or `amount` → per-row rejection under respective buckets.

---

**2) Ingestion Flow Rules (Order is Enforced)**

Order for file and feed ingestion:
1. Parse input (CSV or JSON).
2. Required-field validation (row-level).
3. Status filtering (`record_status` gate if present).
4. Normalization to CanonicalTxn (in-memory only).
5. Semantic classification (ephemeral only).
6. CCT classification (ephemeral only).
7. Aggregation (daily inflow/outflow + daily control buckets).
8. Persistence (derived-only outputs).

Why this order matters:
- Parsing and required-field validation must happen before any classification or aggregation.
- Status filtering is applied only to rows that passed validation, ensuring malformed rows do not influence status-based decisions.
- Classification relies on normalized fields and optional raw hints; it must not run on invalid rows.
- Aggregations must be based only on accepted rows to prevent polluted metrics.
- Persistence is last to guarantee only derived outputs are stored.

---

**3) Record Status & Partial Record Rules**

**record_status handling**
- Applied only if `record_status` column exists.
- Only `SUCCESS` rows proceed.
- Known rejection buckets: `FAILED_INSUFFICIENT_FUNDS`, `FAILED_TIMEOUT`, `FAILED_NETWORK`, `INVALID_TOKEN`.
- Any other value is rejected as `UNKNOWN_STATUS`.

**partial_record handling**
- `partial_record` is a quality flag, not a failure outcome.
- If `partial_record=true` and the row is otherwise valid + `record_status=SUCCESS`, the row is accepted.
- Accepted partial rows are counted in `accepted_partial_rows`.
- Partial status must never cause rejection by itself.

**Rejected row counts**
- Only aggregate counts are recorded and returned.
- No rejected raw rows are stored or returned.

---

**4) Idempotency Rules**

**File ingestion idempotency key**
- `sha256(subject_ref|source|file_hash|min_date|max_date)`
- If declared range is provided, `min_date`/`max_date` come from declared dates; otherwise inferred from data.

**Feed ingestion idempotency key**
- `sha256(subject_ref|source|watermark|min_ts|max_ts|event_count|payload_hash)`
- `payload_hash` is a deterministic hash of the event payload.

**Why transaction IDs are not used**
- Transaction IDs are often sensitive and source-dependent.
- Avoids storing raw identifiers and ensures deterministic, compliance-safe behavior.

**Duplicate handling**
- Any previously seen idempotency key is rejected with `409 Conflict`.

---

**5) Validation & Rejection Rules**

**Row-level rejection buckets**
- `MISSING_REQUIRED_FIELD`
- `INVALID_TS`
- `INVALID_AMOUNT`
- `INVALID_DIRECTION`
- `INVALID_CHANNEL`
- `FAILED_INSUFFICIENT_FUNDS`
- `FAILED_TIMEOUT`
- `FAILED_NETWORK`
- `INVALID_TOKEN`
- `UNKNOWN_STATUS`

**Rejection breakdown semantics**
- Counts only; no raw rows or identifiers returned.
- Status rejections are counted after validation (status gate applies only to valid rows).

**Acceptance ratio guardrail**
- `MIN_ACCEPT_RATIO` default `0.10`.
- If total rows is `0` → `400` (empty batch).
- If accepted rows is `0` → `400` (no valid rows).
- If `MIN_ACCEPT_RATIO` is enabled and `accepted_ratio < MIN_ACCEPT_RATIO` → `400`.
- Set `MIN_ACCEPT_RATIO` to `0`, `0.0`, empty, `none`, or `null` to disable.

---

**6) Semantic Classification Rules**

**Role classification**
- Role classes include `OWNER`, `SUPPLIER`, `OBLIGATION`, `PLATFORM`, `CUSTOMER`, `THIRD_PARTY`, or `UNKNOWN`.

**Purpose classification**
- Purpose classes include `OWNER_TRANSFER`, `INVENTORY`, `OPEX_OR_STATUTORY`, `REFUND_OR_REVERSAL`, `SETTLEMENT_OR_FEE`, `SALE`, `REIMBURSEMENT`, or `UNKNOWN`.

**Signals used**
- Optional `raw_category`, `raw_narration` (ephemeral).
- Channel and direction can influence low-weight heuristics.

**Ephemeral-only**
- Semantic fields are never persisted.
- Classification uses only in-memory data to derive aggregate-only outputs.

---

**7) Cash Control Taxonomy (CCT) Rules**

**CCT enum values**
- `FREE`
- `CONSTRAINED`
- `PASS_THROUGH`
- `ARTIFICIAL`
- `CONDITIONAL`
- `UNKNOWN`

**Bucket meanings**
- `FREE`: discretionary cash flow (e.g., sales).
- `CONSTRAINED`: obligations or necessary spend (rent, utilities, inventory).
- `PASS_THROUGH`: flows that net out (settlements, refunds).
- `ARTIFICIAL`: owner or self-funding transfers.
- `CONDITIONAL`: contingent or reimbursed flows.
- `UNKNOWN`: insufficient or conflicting signals.

**Confidence thresholds**
- Global: `MIN_CCT_CONFIDENCE` (default `0.70`).
- Per-bucket override: `CCT_THRESHOLDS_JSON` (e.g. `{"FREE":0.75}`).

**Ambiguity resolution**
- If multiple candidates compete within `AMBIGUITY_DELTA` (default `0.05`), classification becomes `UNKNOWN`.

**UNKNOWN is forced when**
- Confidence is below threshold.
- Ambiguity exists across competing classifications.
- Signals are missing or contradictory.

---

**8) Aggregation Rules**

**Daily aggregation boundaries**
- Aggregations are computed per calendar day derived from `event_ts.date()`.

**Legacy daily aggregates**
- Daily inflow/outflow totals: `credit` contributes to inflow; `debit` contributes to outflow.

**Daily control-bucket aggregates**
- Counts and sums for each `CCT` bucket, separated by direction (`_IN`, `_OUT`).
- Derived metrics per day:
  - `free_cash_net = FREE_IN - FREE_OUT`
  - `owner_dependency_ratio = ARTIFICIAL_IN / total_in`
  - `pass_through_ratio = (PASS_THROUGH_IN + PASS_THROUGH_OUT) / total_flow`
  - `unknown_flow_ratio = (UNKNOWN_IN + UNKNOWN_OUT) / total_flow`
  - `unique_payers_count`: count of distinct `raw_counterparty_token` values seen that day
  - `accepted_partial_rows`: count of accepted partial rows for that day
  - `unknown_cct_count`: number of rows classified as `UNKNOWN`

**Partial and unknown treatment**
- Partial rows are accepted and counted.
- Unknown CCT rows are included in aggregates under `UNKNOWN_*` buckets.

---

**9) Persistence Rules**

**Allowed to persist**
- Batch metadata: `subject_ref`, `subject_ref_version`, `source`, `idempotency_key`, `file_hash_sha256`, `filename_hash`, `file_ext`, row counts, date range, `cct_unknown_rate`.
- Derived daily inflow/outflow aggregates.
- Derived daily control-bucket aggregates and ratios.

**Explicitly forbidden**
- Raw transaction rows.
- Counterparty identifiers, payer IDs, UPI IDs, account numbers.
- Narrations or statements.
- Any raw event payloads or tokens beyond counts/ratios.

**Storage abstraction**
- All persistence goes through `StoragePort`.
- In-memory sink is dev-only and must remain non-production.
- Future Postgres sink must preserve the same interface and rules.

---

**10) API Response Rules**

**Success response (files and feeds)**
- Must include: `batch_id`, `idempotency_key`, `rows_accepted`, `rows_rejected`, `rejection_breakdown`.
- Must include: `inferred_range` always; `declared_range` if provided.
- Files: `filename_hash`, `file_ext`, `file_hash_sha256`.
- Feeds: `watermark_ts`.
- CCT metrics: `daily_control_days`, `cct_unknown_rate`, `payer_token_present`.

**Rejection response**
- `400` for empty batch, no valid rows, invalid declared range, or acceptance ratio below threshold.
- `409` for duplicate idempotency key.
- No raw rows or identifiers returned.

**Never returned**
- Raw transaction data.
- Narrations, counterparty identifiers, payer tokens.
- Raw filenames.

---

**11) Configuration Rules**

**Configurable thresholds**
- `MIN_ACCEPT_RATIO` default `0.10`, disabled by `0`, `0.0`, empty, `none`, or `null`.
- `MIN_CCT_CONFIDENCE` default `0.70`, disabled by `0` (forces lower threshold to accept).
- `AMBIGUITY_DELTA` default `0.05`.
- `CCT_THRESHOLDS_JSON` for per-bucket overrides.

**Feed-only dev override**
- `ALLOW_MISSING_WATERMARK` must be enabled to honor `allow_missing_watermark=true`.

---

**12) Non-Goals & Guardrails**

This service will never:
- Store raw transaction rows or per-transaction identifiers.
- Store narrations or statements.
- Store payer or counterparty identifiers beyond aggregate counts.
- Make credit decisions or risk judgments.

Anti-patterns to avoid:
- Adding persistence of any raw inputs, even for debugging.
- Logging raw payloads or identifiers.
- Using transaction IDs for idempotency.
- Mixing compliance-sensitive fields into storage tables.

Violating changes include:
- Persisting `merchant_id`, `raw_counterparty_token`, or narration fields.
- Returning raw filenames, payer tokens, or any transaction row.
- Adding direct database writes that bypass `StoragePort`.
