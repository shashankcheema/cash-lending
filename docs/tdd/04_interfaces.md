# Interfaces

## Ingestion
- `ingest_csv(file, metadata) -> IngestionResult`
- `ingest_json(payload, metadata) -> IngestionResult`
- `ingest_statement(file, metadata) -> IngestionResult`

**IngestionResult**
- `batch_id`
- `idempotency_key`
- `record_count`
- `inserted_count`
- `rejected_count`
- `status`
- `error_summary`

## Normalization
- `normalize(raw_record) -> DerivedFeatureInput` (in-memory only)
- `validate(derived_input) -> ValidationResult`

## Feature Builder
- `compute_daily_features(date) -> void`
- `compute_rolling_features(as_of_date, windows[]) -> void`
- `get_feature_freshness() -> date`

## Cash Control (CCT) Classification and Aggregation
- `classify_role_purpose(record) -> txn_semantic`
- `classify_cct(txn_semantic) -> (cct, confidence)`
- `aggregate_daily_control(txns_with_cct) -> daily_control_features`

## Analytics Engine
- `compute_health(subject_ref, as_of_date) -> HealthPacket`
- `compute_ews(subject_ref, as_of_date) -> EWSPacket`

## Risk Engine
- `compute_dp_packet(subject_ref, as_of_date) -> DrawingPowerPacket`
- `compute_fraud_packet(subject_ref, start_date, end_date) -> FraudPacket`

## Simulation Engine
- `run_simulation(params) -> SimulationResult`

## Portfolio APIs
- `get_portfolio_ews(as_of_date, limit) -> EWSSummary[]`
- `get_portfolio_health(as_of_date) -> HealthSummary[]`

## Explainability (Cross-cutting)
- `build_explanations(metrics, decisions, rules) -> Explanation[]`

## Typed Interfaces (Summary)
The typed Python protocols live in this file and include:
- `IngestionService`, `Adapter`, `Normalizer`
- `FeatureRepository`, `AuditRepository`, `BatchRepository`
- `SubjectRefAliasRepository`, `ConsentRepository`
- `FeatureBuilder`, `WindowCalculator`
- `AnalyticsEngine`, `RiskEngine`, `FraudEngine`, `DPCalculator`
