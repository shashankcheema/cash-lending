# Pharmacy Merchant Synthetic Input Pack (RBI-safe Minimal Schema)

**Files**
- `pharmacy_base_90d.csv`
- `pharmacy_stress_90d.csv`
- `pharmacy_fraud_like_90d.csv`

**Schema (v1)**
- `merchant_id`
- `ts`
- `amount`
- `direction`
- `channel`

**Notes**
- No raw identifiers (payer, narration, ref) included.
- Includes credits (sales) and debits (inventory, rent, utilities, fees).
- `ts` uses ISO format with `+05:30` offset.
- Stress scenario: lower volume and occasional extra debits.
- Fraud-like scenario: burstiness, round-amount dominance, and some card-fee debits.

---

## Build Merchant-Realistic Data (Model the Merchant, Not Random Rows)

To make it closer to real transactions, generate data from merchant behavior.

**Merchant Profile (define once)**
- Pick 1 merchant first (e.g., Kirana in Hyderabad) and define:
- Monthly GMV target (e.g., ₹12L/month)
- Txn/day range (weekday vs weekend)
- Channel mix: UPI 70%, Card 20%, Bank 10%
- Ticket size distribution: mostly ₹50–₹600, occasional ₹2k–₹8k
- Working hours: 8:30–22:30
- Seasonality: month start higher, weekends higher
- Concentration: top1 ~8%, top3 ~18% (or whatever you want)
- Debits: inventory purchases, rent, utilities, payouts (if included)

**Generation Strategy (simple but realistic)**
- Generate a calendar (60–180 days)
- For each day:
- Pick `txn_count` ~ Poisson/Normal around baseline
- Generate timestamps concentrated during peak hours
- Generate amounts using log-normal or mixture distribution (small + medium + rare big)
- Enforce weekly seasonality
- Enforce refund rate (e.g., 0.2–0.8%)
- Enforce debits (weekly inventory purchase + monthly rent)
- Output to CSV in the minimal schema
