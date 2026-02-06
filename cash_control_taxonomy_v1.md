# Cash Control Taxonomy v1 (RBI-safe, Derived-Only Storage)

**Goal:** Classify cash movements into **control buckets** so the platform measures **repayment-relevant cash**, not just “money that touched the account.”

This spec is designed for **cash-flow underwriting** where **raw transactions / statements are processed ephemerally** and **only derived aggregates are stored**.

---

## 1. Definitions

### 1.1 Transaction (ephemeral input)
A raw transaction row from UPI/bank/card sources (including statement fields like counterparty text, tags, notes) that is **read only in memory** for classification and aggregation.

### 1.2 Control Buckets (Cash Control Type — CCT)
Each transaction is mapped to exactly one **Cash Control Type**.

| CCT | Meaning | Underwriting interpretation |
|---|---|---|
| **FREE** | Discretionary cash that can be redirected to repayment | Positive repayment capacity |
| **CONSTRAINED** | Operationally required flows (core business obligations) | Mandatory; reduces free cash |
| **PASS_THROUGH** | Temporary flows that do not represent sustainable earnings | Do not count as revenue; low quality |
| **ARTIFICIAL** | Non-operating support (owner infusions/withdrawals) | Increases fragility/dependence |
| **CONDITIONAL** | Cash dependent on external/uncertain conditions | Discounted; timing risk |
| **UNKNOWN** | Low confidence classification | Risk flag; requires conservatism |

**Important:** CCT is derived ephemerally and **must not require storing identities**.

---

## 2. How CCT Relates to Role/Purpose Semantics

CCT sits **above** role/purpose classification.

- **Role** answers: *who is involved?* (customer/supplier/platform/owner/utility/unknown)
- **Purpose** answers: *why did money move?* (sale/inventory/opex/settlement/refund/fee/owner_transfer/unknown)
- **CCT** answers: *can this cash support repayment?*

Typical mapping (guideline):
- `sale` → **FREE** (unless heavy returns/chargebacks suggest PASS_THROUGH)
- `inventory`, `rent`, `utilities` → **CONSTRAINED**
- `settlement`, `refund`, `fee` → **PASS_THROUGH**
- `owner_transfer` → **ARTIFICIAL**
- `insurance_reimbursement`, `subsidy`, `claim` → **CONDITIONAL**

---

## 3. Classification Inputs (Ephemeral Only)

### 3.1 Allowed ephemeral signals
Read transiently and discard:
- direction (credit/debit)
- amount
- timestamp
- channel (UPI/BANK/CARD)
- raw category/tag strings (e.g., “Medical”, “Money Transfer”)
- raw counterparty text (merchant name / UPI handle text)
- raw note/narration
- recurrence patterns within the batch (frequency, periodicity)

### 3.2 Prohibited at-rest signals
- payer/payee identifiers, UPI IDs, account numbers, raw counterparty strings, narrations, reference numbers

---

## 4. Decision Procedure (Rules v1)

### 4.1 Outputs
For each transaction:
- `purpose_class`
- `cct` ∈ {FREE, CONSTRAINED, PASS_THROUGH, ARTIFICIAL, CONDITIONAL, UNKNOWN}
- `confidence` ∈ [0, 1]

If `confidence < τ` (default τ=0.6): set `cct=UNKNOWN`.

### 4.2 Rule priorities (first match wins)
1. Fees/charges → PASS_THROUGH
2. Refunds/reversals → PASS_THROUGH
3. Owner transfers → ARTIFICIAL
4. Platform settlements → PASS_THROUGH
5. Inventory + operating expenses → CONSTRAINED
6. Retail sales → FREE
7. Reimbursements/claims/subsidies → CONDITIONAL
8. Else → UNKNOWN

### 4.3 Confidence scoring (simple v1)
Start with base confidence from purpose classifier and adjust:
- +0.15 if pattern strongly matches expected pharmacy behavior
- +0.15 if recurring weekly supplier debit pattern
- -0.20 if conflicting signals (e.g., “sale” but very large round amount with owner-like recurrence)

---

## 5. Aggregates to Persist (Derived Only)

### 5.1 Daily control buckets
Persist per (merchant_id, date):
- `free_in_sum`, `free_in_count`
- `constrained_out_sum`, `constrained_out_count`
- `pass_through_in_sum`, `pass_through_out_sum`
- `artificial_in_sum`, `artificial_out_sum`
- `conditional_in_sum`, `conditional_out_sum`
- `unknown_in_sum`, `unknown_out_sum`

Derived daily KPIs:
- `free_cash_net = free_in_sum - constrained_out_sum - pass_through_out_sum`
- `owner_dependency_ratio = artificial_in_sum / NULLIF(total_in_sum, 0)`
- `pass_through_ratio = pass_through_in_sum / NULLIF(total_in_sum, 0)`
- `unknown_flow_ratio = (unknown_in_sum + unknown_out_sum) / NULLIF(total_abs_flow, 0)`

### 5.2 Rolling stability (future layers)
For 7/14/30/90:
- mean/std of `free_cash_net`
- drawdowns
- trend of owner dependency

---

## 6. Explainability Requirements
All decisions must reference derived metrics + rule ids + policy version.

---

## 7. Guardrails
- No raw persistence (schema lint)
- No raw logs (redaction)
- Ephemeral-only processing

---

## 8. Versioning
Any change requires bumping `policy_version`.
