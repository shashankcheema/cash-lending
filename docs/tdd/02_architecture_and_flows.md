# Architecture and Flows

## System Components
1. Ingestion API: receives files and feeds.
2. Adapter Layer: maps raw formats to derived feature inputs (ephemeral).
3. Ephemeral Input Handler: processes raw inputs in-memory only, no raw data at rest.
4. Feature Builder Jobs: daily and rolling features.
5. Feature Store: derived aggregates for fast reads.
6. Analytics Engine: health score and EWS.
7. Risk Engine: DP and fraud rules.
8. Simulation Engine: loan and collections simulation.
9. API Layer: subject and portfolio outputs.
10. Dashboard UI: NBFC and operator views.

## Data Flow Overview
Ephemeral Inputs → Adapter → Derived Features → Feature Jobs → Feature Store → (Analytics/Risk) → API → Dashboard

## Component Interaction Diagrams (Render-Safe)
(See render-safe diagrams in `docs/tdd/02a_diagrams_render_safe.md`. Canonical diagrams live in `docs/tdd/06_diagrams_canonical.md`.)

## Deployment Evolution
- Single-node MVP: all services on one VM or pod.
- Scaled batch: split services, read replicas, scheduled jobs.
- Streaming-ready: event bus, windowed aggregates, real-time feature store.

## Data Lineage
Ephemeral Inputs → Adapters → Derived Feature Inputs → Feature Store → Daily and Rolling Features → Analytics and Risk → APIs → Dashboards

## Sequence Flows (Render-Safe)
Includes ingestion, feature computation, analytics, DP, fraud, simulation, and portfolio EWS flows.

---
