# Project Taxonomy (Terms and Definitions)

This document is the **canonical glossary** for the cash‑flow lending platform and related ingestion services. It defines the **exact terms** used across docs, code, and APIs. It is designed to reduce ambiguity and prevent drift as the project grows.

---

## 1) Identity and Privacy

**subject_ref**  
Opaque, non‑PII subject identifier used everywhere in persistence, idempotency, and aggregation. It is the only durable identity in this system.

**subject_ref_version**  
Alias version used for re‑keying/rotation. Multiple aliases may be active during migration.

**Identity Vault**  
External, partner‑owned system that maps subject_ref ↔ real‑world identity. Not part of this platform.

**PII**  
Personally Identifiable Information. Must never be persisted in this platform.

**No Raw Merchant Data at Rest**  
Policy constraint: no raw transactions, bank statements, payer IDs, narrations, or counterparty identifiers at rest. Only derived aggregates and output packets are persisted.

---

## 2) Inputs and Ephemeral Fields

**Ephemeral Inputs**  
Raw transaction‑like records processed in memory only. Not stored in persistence layers.

**merchant_id**  
Input‑only field for validation/debug. **Allowed in payloads**, **forbidden at rest**.

**payer_token**  
Preferred optional input column for unique payer counting. Ephemeral only, never persisted.

**raw_counterparty_token**  
Alias for payer_token from Paytm‑like feeds. Ephemeral only.

**raw_narration / raw_category**  
Optional input signals used for semantic and CCT classification. Ephemeral only.

**partial_record**  
Optional input quality flag. Used only for counts; never persisted as raw data.

---

## 3) Canonical In‑Memory Structures

**CanonicalTxn (Ephemeral)**  
In‑memory normalized transaction used for validation and aggregation. Contains `subject_ref`, `merchant_id`, `event_ts`, `amount`, `direction`, `channel`, plus optional ephemeral signals.

**TxnSemantic (Ephemeral)**  
Derived semantic representation of a transaction: role_class and purpose_class, plus original signals for in‑memory use.

**CCTResult (Ephemeral)**  
Classification output: `cct`, `confidence`, and optional `rules_fired`. Never persisted.

---

## 4) Cash Control Taxonomy (CCT)

**CCT (Cash Control Type)**  
Canonical enum used across the platform:
```
FREE, CONSTRAINED, PASS_THROUGH, ARTIFICIAL, CONDITIONAL, UNKNOWN
```

**FREE**  
Discretionary true business inflow/outflow (e.g., sales revenue; normal operating spend not contractually locked).

**CONSTRAINED**  
Obligations reducing cash flexibility (rent, utilities, inventory replenishment, EMI, statutory payments).

**PASS_THROUGH**  
Flows not truly owned cash (platform settlements, gateway netting, mirrored refunds, fees).

**ARTIFICIAL**  
Owner or related‑party movements (infusions/withdrawals).

**CONDITIONAL**  
Reimbursements/insurance/claims/contingent receipts or payouts.

**UNKNOWN**  
Low confidence or unclassifiable after ambiguity handling.

**MIN_CCT_CONFIDENCE**  
Minimum confidence threshold. If top candidate < threshold → UNKNOWN. Default 0.70 (0 disables).

**AMBIGUITY_DELTA**  
If top‑2 candidates are within this delta and disagree → UNKNOWN. Default 0.05.

**CCT_THRESHOLDS_JSON**  
Optional per‑bucket overrides for confidence thresholds.

---

## 5) Aggregates and Derived Metrics

**daily_control_aggs**  
Per‑day control bucket aggregates (counts + sums) and derived ratios. Persisted only as derived data.

**Control Buckets (Daily)**  
Counts and sums by bucket and direction:
`FREE_IN`, `FREE_OUT`, `CONSTRAINED_IN`, `CONSTRAINED_OUT`, `PASS_THROUGH_IN`, `PASS_THROUGH_OUT`,
`ARTIFICIAL_IN`, `ARTIFICIAL_OUT`, `CONDITIONAL_IN`, `CONDITIONAL_OUT`, `UNKNOWN_IN`, `UNKNOWN_OUT`.

**free_cash_net**  
`FREE_IN - FREE_OUT`

**owner_dependency_ratio**  
`ARTIFICIAL_IN / max(1e-9, total_in)`

**pass_through_ratio**  
`(PASS_THROUGH_IN + PASS_THROUGH_OUT) / max(1e-9, total_flow)`

**unknown_flow_ratio**  
`(UNKNOWN_IN + UNKNOWN_OUT) / max(1e-9, total_flow)`

**unique_payers_count**  
Daily unique count computed from payer_token (ephemeral); only the count is persisted.

**unknown_cct_count**  
Count of events classified as UNKNOWN after threshold/ambiguity handling.

**cct_unknown_rate**  
Batch‑level ratio: `unknown_cct_count / total_count`. Persisted as batch metadata.

---

## 6) Feature Store Tables (Derived Only)

**merchant_daily_features**  
Authoritative daily aggregates keyed by `subject_ref` + date. Includes CCT buckets and optional legacy metrics.

**merchant_rolling_features**  
Rolling windows (7/14/30/90) derived from daily aggregates. Keyed by `subject_ref` + date + window.

**feature_freshness_watermarks**  
Latest completion marker for daily/rolling jobs.

---

## 7) Output Packets (Derived Only)

**merchant_health_packets**  
Health score, EWS flags, explanations per subject_ref and as_of_date.

**merchant_dp_packets**  
Drawing Power (limit + available), haircuts, explanations per subject_ref and as_of_date.

**merchant_fraud_packets**  
Fraud score, flags, explanations over a date range.

---

## 8) Idempotency and Batch Metadata

**idempotency_key**  
Deterministic batch key:
```
sha256(subject_ref + source + file_hash + min_date + max_date)
```
If `input_start_date` and `input_end_date` are provided, those dates are used.

**feature_input_batches**  
Metadata‑only batch table: subject_ref, source_type, counts, declared range, checksum, TTL, idempotency key.

**declared_range**  
User‑provided input date range; used for idempotency and validation.

**inferred_range**  
Min/max timestamps inferred from parsed rows; must fall within declared range if provided.

---

## 9) Ingestion and Validation

**Ingestion API**  
Accepts CSV or JSON feeds, validates in‑memory, computes derived aggregates, persists derived outputs only.

**record_status**  
Optional Paytm‑like field. If present, only `SUCCESS` rows are accepted.

**accepted_partial_rows**  
Count of rows marked `partial_record == true` that were accepted.

**MIN_ACCEPT_RATIO**  
Guardrail for minimum accepted/total rows in a batch.

---

## 10) Analytics and Risk

**Health Score**  
Composite score derived from stability, density, concentration, anomalies, and CCT signals.

**EWS (Early Warning Signals)**  
Rule‑based triggers on drops, spikes, anomalies, or CCT deterioration.

**DP (Drawing Power)**  
Dynamic credit limit based on sales/flows and risk haircuts.

**Fraud / Mule Score**  
Rule‑based score derived from concentration, periodicity, burstiness, and anomaly patterns.

---

## 11) Simulation and Collections

**Simulation Engine**  
Generates loan lifecycle + collections outcomes for validation without production rails.

**Collections Simulator**  
Models retries, failures, and rail‑specific behavior (UPI/NACH).

---

## 12) Policies and Guardrails

**TTL / Purge**  
Ephemeral inputs must be purged within 24 hours (or earlier) with audit evidence.

**Audit Events**  
Metadata‑only logs of ingestion, job runs, API calls, policy changes, and purge activity.

---

## 13) Diagram Types

**Render‑Safe Diagrams**  
Sanitized Mermaid diagrams that avoid special characters for strict renderers.

**Canonical Diagrams**  
Full‑fidelity Mermaid diagrams used for design intent; may not render in strict environments.

---

## 14) Versioning

**policy_version**  
Version tag for DP, fraud, EWS, and CCT policies. Any rule changes must bump policy_version.

---

## 15) Source of Truth

**Docs**  
`docs/tdd/` contains authoritative design documentation.

**Code**  
`cashflow_ingest/` implements the ingestion boundary and derived‑only persistence.
