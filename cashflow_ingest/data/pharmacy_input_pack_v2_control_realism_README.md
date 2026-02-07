# Pharmacy Input Pack v2 (Cash Control Realism)

This pack contains two variants for each scenario.

## 1) Paytm-like CSVs (for classifier development)
These files include *ephemeral-only* columns to simulate statement tags/notes.

- pharmacy_paytm_like_base_05Nov25_04Feb26.csv
- pharmacy_paytm_like_stress_05Nov25_04Feb26.csv
- pharmacy_paytm_like_fraud_like_05Nov25_04Feb26.csv

Columns:
- merchant_id, ts, amount, direction, channel
- raw_category, raw_note  (simulate statement context; ingestion must NOT store/log)
- role_hint, purpose_hint, cct_hint (GROUND TRUTH for testing; ingestion must DROP)

## 2) Minimal RBI-safe uploads (for ingestion API testing)
- pharmacy_minimal_base_05Nov25_04Feb26.csv
- pharmacy_minimal_stress_05Nov25_04Feb26.csv
- pharmacy_minimal_fraud_like_05Nov25_04Feb26.csv

Columns:
- merchant_id, ts, amount, direction, channel

Date range: 2025-11-05 to 2026-02-04 (synthetic)
Timezone offset: +05:30

Scenarios:
- Base: normal pharmacy behavior
- Stress: lower sales volume + occasional emergency inventory debit
- Fraud-like: burstiness + round-amount dominance + extra platform fee debits

Compliance:
- No identities/UPI IDs/narrations are included; raw_note is generic.
- Production storage remains derived-only.
