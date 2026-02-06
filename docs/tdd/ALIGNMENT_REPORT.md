# TDD Alignment Report

## Scope
This report verifies alignment across the consolidated TDD files in `docs/tdd/`.

## Checks (Pass/Fail)

### Identity and Storage Policy
- [x] `subject_ref` used as the primary identifier across docs.
- [x] No raw merchant data at rest policy present and consistent.
- [x] No `transactions` table or raw statement rows described.
- [x] Idempotency uses `idempotency_key` (no `txn_id`).

### Data Flow and Schemas
- [x] Inputs are ephemeral; only derived features stored.
- [x] Feature store tables are `merchant_daily_features` and `merchant_rolling_features` keyed by `subject_ref`.
- [x] Output packets only (health, DP, fraud) are persisted.
- [x] Consent metadata table defined without PII.

### Interfaces and Contracts
- [x] Interfaces use `subject_ref` and `idempotency_key`.
- [x] Normalization is explicitly in-memory only.

### NFRs and Ops
- [x] TTL <= 24 hours and purge evidence required.
- [x] Observability and audit requirements are metadata-only.

### Diagrams
- [x] Canonical diagrams align with `subject_ref` terminology.
- [x] Render-safe diagrams align with no-raw-storage policy.

## Files Reviewed
- `docs/tdd/01_overview.md`
- `docs/tdd/02_architecture_and_flows.md`
- `docs/tdd/02a_diagrams_render_safe.md`
- `docs/tdd/03_data_and_schema.md`
- `docs/tdd/04_interfaces.md`
- `docs/tdd/05_operations_and_quality.md`
- `docs/tdd/06_diagrams_canonical.md`

## Notes
- All alignment checks passed in the current repository state.
