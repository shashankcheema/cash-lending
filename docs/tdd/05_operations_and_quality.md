# Operations and Quality

## Acceptance Criteria
The MVP is complete when:
- Ingestion succeeds with validation and audit logs.
- Duplicate inputs are rejected via idempotency.
- Feature pipelines compute daily and rolling features for any historical date.
- Health, EWS, DP, and fraud packets are produced with explainability.
- Simulation runs end-to-end and produces repayment outcomes.
- Dashboards render and support drill-down.

## Non-Functional Requirements
### Availability and Reliability
- API availability: 99.5% monthly (read endpoints).
- Ingestion availability: 99.0% monthly (batch uploads).
- RPO: 24 hours.
- RTO: 4 hours staging, 8 hours production MVP.

### Performance and Latency
- 100k-row CSV ingestion: < 5 minutes end-to-end (parse → derived features).
- Daily feature job for 10k subjects: < 30 minutes.
- Rolling feature job for 10k subjects: < 45 minutes.
- Subject analytics API p95: < 500 ms cached, < 2.5 s uncached.
- Portfolio EWS API p95: < 2.5 s for top 100.

### Scalability Targets
- Support 1M transactions per month on a single primary DB instance.
- Feature store size: < 50 GB for MVP datasets.
- Backfill 90 days of history in < 6 hours.

### Data Quality and Consistency
- Idempotency: duplicate inputs with the same idempotency_key rejected 100%.
- Feature freshness watermark updated daily by 08:00 local time.
- Schema validation coverage >= 95% of required fields per source type.

### Security and Privacy
- Encrypt data in transit and at rest.
- No PII at rest (no payer identifiers, narrations, or reference data stored).
- RBAC with audit logs for all write operations.
- Retention: no raw uploads at rest; ephemeral TTL <= 24 hours with verified purge.

### Observability
- Structured logs for ingestion, feature jobs, analytics, and risk calls.
- Metrics: ingestion success rate, job duration, feature freshness lag, API latency.
- Alerting: feature freshness lag > 24 hours, ingestion failure rate > 5% daily.

### Testing and Release Quality
- Unit test coverage >= 80% on core engines.
- Golden test suites for ingestion, features, DP, fraud with fixed synthetic data.
- All schema migrations reviewed and applied in staging before production.

## Storage Policy Enforcement
- Purge job runs hourly (or every 30 minutes) plus startup sweep.
- Pessimistic purge: delete earlier if batch completes successfully.
- Purge evidence recorded as audit_event metadata only.

## Open Questions
- Target scale (subjects, txns per day) for MVP and post-MVP.
- Preferred deployment environment (cloud vs on-prem).
- Dashboard users and RBAC roles.
- Feature store choice at scale (Postgres vs ClickHouse).
- Exact DP coefficients and thresholds.

## Document Acceptance Criteria
- Every major component has a defined interaction sequence.
- DP, fraud, health, and EWS flows are fully explainable.
- Engineers can implement modules independently using these docs.
- Regulated data sources can be added via adapters without changing core flows.
