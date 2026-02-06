## 3.0 Data Storage Policy (RBI / AA Minimization)

**No Raw Subject Data at Rest**
- Raw transactions, bank statements, and payer identifiers must never be persisted.
- Only aggregated features and analytic or risk output packets are stored.
- Temporary input handling must be ephemeral with TTL and purge enforced.
- Audit logs store metadata only and must exclude PII or raw payloads.

# Canonical Mermaid Diagrams (Rich Labels)

These are the **canonical** versions of key diagrams with richer labels, line breaks, and semantics. Some Mermaid renderers are strict and may fail on these. The render-safe versions remain in `cash_flow_lending_platform_step_by_step_implementation_plan (2).md`.

## 3A. Component Interaction Diagrams (C4-style)

### 3A.1 C4 Level 1 — System Context
```mermaid
flowchart LR
subgraph External[External Actors or Systems]
NBFC[NBFC or Risk Team]
OPS[Ops or Analysts]
DEV[Developers or Testers]
DS[Public or Synthetic Datasets]
EXTAA[AA future]
EXTGST[GSTN or GSP future]
EXTUPI[UPI PSP or Acquirer future]
EXTOCEN[OCEN Rail future]
end

subgraph System[Cash-Flow Lending Platform This System]
API[Platform APIs]
DASH[Dashboards]
CORE[Underwriting & Monitoring Core]
end

DEV -->|Upload CSV or JSON or Statements| API
DS -->|Seed data| API
NBFC -->|View portfolio risk| DASH
OPS -->|Monitor EWS & collections| DASH
DASH -->|Query metrics| API
API -->|Risk & analytics outputs| DASH

EXTAA -.->|Bank or GST feeds later| API
EXTGST -.->|GST filings later| API
EXTUPI -.->|UPI txn metadata later| API
EXTOCEN -.->|Loan origination or disbursal later| API

API --> CORE
```

### 3A.2 C4 Level 2 — Container Diagram
```mermaid
flowchart TB
subgraph Platform[Cash-Flow Lending Platform]
UI[Dashboard UI Web]
APIGW[API Layer or Gateway REST]
ING[Ingestion Service Ephemeral Uploads or Feeds]
ADP[Adapter Layer CSV or JSON or Statement]
NORM[Normalization Service Type enforcement, canonical schema]
FS[Feature Store Postgres or Parquet]
JOB[Job Runner or Scheduler Cron]
FB[Feature Builder Daily + Rolling]
AE[Analytics Engine Health + EWS]
RE[Risk Engine DP + Fraud]
SIM[Simulation Engine Loan + Collections]
AUD[Audit Log Store]
MET[Metrics or Logs or Tracing]
end

UI -->|REST queries| APIGW
APIGW --> AE
APIGW --> RE
APIGW --> SIM

APIGW --> ING
ING --> ADP
ADP --> NORM
NORM --> FS
ING --> AUD

JOB --> FB
FB --> FS
FB --> AUD

AE --> FS
RE --> FS
SIM --> RE
SIM --> AUD

ING --> MET
FB --> MET
AE --> MET
RE --> MET
SIM --> MET
APIGW --> MET
```

### 3A.3 C4 Level 3 — Component Diagram (Risk Engine)
```mermaid
flowchart LR
subgraph RE[Risk Engine]
RAPI[Risk Facade compute_dp_packet, compute_fraud_packet]
FF[Feature Fetcher read FS]
DPC[DP Calculator base + caps + haircuts]
OUST[Outstanding Provider simulator in v1]
FRAUD[Fraud Engine]
RG[Rule Graph Executor groups + weighting]
EVID[Evidence Builder explanations]
AGG[Risk Packet Assembler]
end

FS[Feature Store] --> FF
DS[Debt or Outstanding Store] --> OUST

RAPI --> FF
RAPI --> DPC
RAPI --> FRAUD
DPC --> OUST
FRAUD --> RG
RG --> EVID
DPC --> AGG
EVID --> AGG
OUST --> AGG
AGG --> RAPI
```

### 3A.4 C4 Level 3 — Component Diagram (Analytics Engine)
```mermaid
flowchart LR
subgraph AE[Analytics Engine]
AAPI[Analytics Facade compute_health, compute_ews]
FF[Feature Fetcher read FS]
HSC[Health Scoring Core components + weights]
EWS[EWS Rule Engine triggers + severity]
REC[Recommendation Builder actions]
EX[Explainer why + top contributors]
OUT[Packet Assembler]
end

FS[Feature Store] --> FF

AAPI --> FF
AAPI --> HSC
AAPI --> EWS
EWS --> REC
HSC --> EX
EWS --> EX
REC --> OUT
EX --> OUT
OUT --> AAPI
```

### 3A.5 C4 Level 3 — Component Diagram (Feature Builder)
```mermaid
flowchart LR
subgraph FB[Feature Builder]
RUN[Job Runner Entry run_daily, run_rolling]
Q[Txn Query read features]
AGG[Aggregator groupby subject_ref]
FEAT[Feature Calculator metrics + ratios]
WIN[Window Calculator 7 or 14 or 30 or 90]
UPS[Upserter write FS]
WM[Watermark or Freshness write marker]
AUD[Audit Emitter]
end

FS[Feature Store] --> Q
Q --> AGG
AGG --> FEAT
FEAT --> UPS
FEAT --> WIN
WIN --> UPS
UPS --> FS[Feature Store]
RUN --> Q
RUN --> WM
RUN --> AUD
AUD --> AUDS[Audit Log Store]
```

### 3A.6 C4 Level 3 — Component Diagram (Ingestion + Normalization)
```mermaid
flowchart LR
subgraph ING[Ingestion Service Ephemeral]
END[Upload Endpoints or ingest or *]
VAL[Schema Validator]
PAR[Parser]
DED[Deduplicator batch + idempotent keys]
ADP[Adapter Selector]
MAP[Adapter Mapper CSV or JSON or Statement]
NORM[Normalizer types + canonical]
BULK[Bulk Persist write features]
AUD[Audit Emitter]
end

END --> VAL
VAL --> PAR
PAR --> DED
DED --> ADP
ADP --> MAP
MAP --> NORM
NORM --> BULK
BULK --> FS[Feature Store]
AUD --> AUDS[Audit Log Store]
END --> AUD
```

## 3C. Deployment Diagram (Streaming-Ready)

### 3C.3 Streaming-Ready (Near real-time features)
```mermaid
flowchart TB
subgraph Ingest[Ingestion]
UPI[UPI or PSP Feed Adapter]
AA[AA Adapter]
GST[GST Adapter]
end

K[Kafka or Event Bus]

subgraph Stream[Streaming Compute]
ST[Stream Processor windowed aggregates]
FEAT[Realtime Feature Store]
end

subgraph Serving[Serving]
API[API Service]
AE[Analytics]
RE[Risk]
UI[Dashboard]
end

FS[Long-term Feature Store Parquet or Postgres]

UPI --> K
AA --> K
GST --> K
K --> ST
ST --> FEAT
ST --> FS

API --> FEAT
AE --> FEAT
RE --> FEAT
UI --> API
```

## 3D. Data Lineage Diagram
```mermaid
flowchart LR
RAW[Ephemeral Inputs CSV or JSON or Statements or UPI or AA] --> ADP[Adapters]
ADP --> NORM[Derived Feature Inputs ephemeral]
NORM --> FS[Feature Store]

FS --> DAILY[Daily Feature Job]
DAILY --> MDF[merchant_daily_features]

MDF --> ROLL[Rolling Window Job]
ROLL --> MRF[merchant_rolling_features]

MDF --> AE[Analytics Engine Health + EWS]
MRF --> AE

MDF --> RE[Risk Engine DP + Fraud]
MRF --> RE

RE --> API[APIs]
AE --> API

API --> DASH[Dashboards Subject or Portfolio]

subgraph Outputs[Outputs]
HEALTH[Health Packets]
EWS[EWS Packets]
DP[DP Packets]
FRAUD[Fraud Packets]
end

AE --> HEALTH
AE --> EWS
RE --> DP
RE --> FRAUD
HEALTH --> DASH
EWS --> DASH
DP --> DASH
FRAUD --> DASH
```

## 13A. Component-Level Sequence Diagrams

### 13A.3 Daily Feature Job — Compute + Write + Freshness Marker
```mermaid
sequenceDiagram
participant J as Scheduler
participant FB as FeatureBuilderJob
participant T as Feature Store
participant AG as Aggregator
participant FS as Feature Store
participant M as Feature Freshness Marker
participant AU as Audit Log

J->>FB: Run for date=D
FB->>T: Query derived feature inputs where date(ts)=D for all directions
T-->>FB: txns[]
FB->>AG: Group by subject_ref and compute daily aggregates
AG-->>FB: daily_features_by_subject[]
FB->>FS: Upsert merchant_daily_features (PK subject_ref,date)
FS-->>FB: ok
FB->>M: Write watermark (features_ready_for=D)
M-->>FB: ok
FB->>AU: Log job run (duration, subjects, failures)
AU-->>FB: ok
FB-->>J: job success
```

## 13B. Canonical Diagrams (C4 + Code-Level)

### 13B.1 System Context Diagram (C4 – Level 1)
```mermaid
flowchart LR
User[Analyst or Operator]
NBFC[NBFC Risk or Ops Team]
Ext[External Data Sources CSV, Bank Export, Synthetic]

System[Cash-Flow Lending Platform]

User -->|Uploads data, runs simulations| System
NBFC -->|Views dashboards, risk outputs| System
Ext -->|Transaction-like data| System
```

### 13B.2 Fraud Rule Graph Executor — Code-Level Structure
```mermaid
flowchart LR
subgraph FR[Fraud Engine]
ENTRY[score_fraud] --> PREP[preprocess_metrics]
PREP --> G1[Concentration Rules]
PREP --> G2[Periodicity Rules]
PREP --> G3[Time-of-Day Rules]
PREP --> G4[Amount Pattern Rules]
PREP --> G5[Burst Rules]

G1 --> AGG
G2 --> AGG
G3 --> AGG
G4 --> AGG
G5 --> AGG

AGG[aggregate_scores] --> SCORE[compute_fraud_score]
SCORE --> EXPL[build_evidence]
end
```

### 13B.3 Window Calculator — Code-Level Structure
```mermaid
flowchart TB
subgraph WIN[Rolling Window Calculator]
API[compute_windows] --> LOAD[load_daily_features]
LOAD --> SORT[sort_by_date]
SORT --> W7[calc_7d]
SORT --> W14[calc_14d]
SORT --> W30[calc_30d]
SORT --> W90[calc_90d]

W7 --> MERGE
W14 --> MERGE
W30 --> MERGE
W90 --> MERGE

MERGE[merge_windows] --> WRITE[write_feature_store]
end

FS[Feature Store] --> LOAD
```

---

## Cash Control (CCT) Layer — NEW Canonical Step

This platform measures **repayment-relevant cash**, not just “money that touched the account.”

### Key idea
During ingestion, we classify each transaction ephemerally into a **Cash Control Type (CCT)**:

- **FREE**: discretionary cash that can service debt
- **CONSTRAINED**: mandatory operational outflows (inventory, rent, utilities)
- **PASS_THROUGH**: settlements, fees, refunds, reversals (do not count as revenue)
- **ARTIFICIAL**: owner infusions/withdrawals (dependency signal)
- **CONDITIONAL**: reimbursements/claims/subsidies (timing risk)
- **UNKNOWN**: low-confidence classification (risk flag)

**Compliance:** CCT is derived in-memory using statement text/tags if available, then **discarded**. Only **derived aggregates** per day/window are stored.

### What changes downstream
- Feature store persists **control-bucket aggregates** (e.g., `free_in_sum`, `constrained_out_sum`, `owner_dependency_ratio`).
- DP, EWS, and Fraud consume **FREE cash stability** and **owner-dependence** as first-class metrics.
