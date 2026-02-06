# Data and Schema (Authoritative)

## Identifier Strategy (subject_ref)
- Authoritative source: external Subject Registry or Partner CRM or LOS-LMS.
- Mapping storage: external Identity Vault with separate access control and retention.
- Rotation and re-keying: supported via versioned aliases with effective windows.
- Migration: allow multiple active aliases during re-keying; old aliases remain queryable for audit windows.

## Idempotency (No txn_id)
Idempotency key per batch:
```
idempotency_key = sha256(subject_ref + source_type + input_start_date + input_end_date + file_checksum_sha256)
```
Behavior: if `idempotency_key` already exists in `feature_input_batches`, return prior result (200) or 409 per API policy.

## No Raw Subject Data at Rest
- Raw transactions, bank statements, and payer identifiers are never persisted.
- Only derived metrics and output packets are stored.
- Temporary input handling is ephemeral with TTL and purge.

## Ingestion Metadata (No Raw Payloads)
### feature_input_batches (metadata only)
- `batch_id`
- `subject_ref`, `subject_ref_version`
- `source_type`, `received_at`, `record_count`, `rejected_count`
- `date_range_start`, `date_range_end`
- `checksum`, `idempotency_key`, `expires_at`, `status`

### subject_ref_aliases (versioned aliases)
- `subject_ref`, `subject_ref_version`, `effective_from`, `effective_to`, `status`

### consent_artifacts (metadata only)
- `consent_id`, `subject_ref`, `fi_type`, `purpose_code`
- `consent_start`, `consent_expiry`, `frequency`, `fetch_mode`, `status`
- `receipt_checksum`

## Aggregated Feature Store (Derived Only)
### merchant_daily_features (PK: subject_ref, date)
- `txn_count`, `sales_sum`, `unique_payers`
- `avg_ticket`, `ticket_variance`
- `night_ratio`, `weekend_ratio`
- `top1_concentration`, `top3_concentration`, `top5_concentration`
- `round_amount_ratio`, `tiny_amount_ratio`, `burstiness_score`

### merchant_rolling_features (PK: subject_ref, as_of_date, window_days)
- `rolling_sales`, `rolling_txn_count`, `rolling_volatility`, `rolling_trend`
- `rolling_customer_growth`, `rolling_concentration_trend`

### feature_freshness_watermarks
- `watermark_key`, `last_ready_date`, `updated_at`

## Unique Payer Computation (Privacy-Safe)
- `unique_payers` is computed in-memory per batch from ephemeral counterparty tokens.
- Rolling unique payers derived from daily counts or optional HLL sketches.
- If sketches are stored, only the sketch blob is persisted (no identifiers).

## Analytics and Risk Output Packets (Only)
### subject_health_packets
- `subject_ref`, `as_of_date`, `health_score`, `ews_flags`, `explanations`, `policy_version`

### subject_dp_packets
- `subject_ref`, `as_of_date`, `dp_limit`, `dp_available`, `haircuts`, `explanations`, `policy_version`

### subject_fraud_packets
- `subject_ref`, `start_date`, `end_date`, `fraud_score`, `fraud_flags`, `explanations`, `policy_version`

## Audit (Metadata Only)
- `audit_events` with `event_type` including `PURGE`
- Metadata only: batch_id, purged_at, purge_method, artifact_count_deleted, storage_path_hash

## Cash Control Axis (CCT)
CCT is computed ephemerally and only derived control-bucket aggregates are stored.
Persisted daily fields include free, constrained, pass-through, artificial, conditional, and unknown flows, plus derived ratios.
