#!/usr/bin/env python3
"""
Pharmacy Synthetic Data Generator (v5)
Language: Python

Purpose
-------
Generate realistic, Paytm-like transaction datasets for a single pharmacy MSME that support:
- Ingestion + normalization development
- Role/Purpose + Cash Control (CCT) classifier development (using EPHEMERAL fields)
- Robust scenario testing: base, stress, fraud_like
- Negative testing: insufficient funds, timeout/network failures, partial records, invalid tokens
- Seasonal trends: full-year generation (365 days)
- Chronic refill behavior with missed/late refills (stress amplification)

Compliance Alignment (IMPORTANT)
-------------------------------
- Do NOT store any real merchant/customer data. This generator produces SYNTHETIC-only data.
- Fields prefixed with `raw_` and all `*_hint` fields + failure fields are EPHEMERAL-ONLY
  intended for classifier/QA testing. Your production ingestion MUST:
  - DROP: raw_category, raw_note, raw_counterparty_token, role_hint, purpose_hint, cct_hint,
          record_status, failure_reason, partial_record
  - NEVER store/log them at rest.
- Minimal RBI-safe exports include ONLY:
  merchant_id, ts, amount, direction, channel

Diversified payment rails (India)
--------------------------------
- UPI, CARD, BANK
- NET_BANKING: larger supplier payments
- WALLET: Paytm/PhonePe wallet-like receipts/fees/settlements
- COD_SETTLEMENT: delivery COD settlement batches (credit settlements)

Output Files
------------
Paytm-like:
- pharmacy_paytm_like_{scenario}_v5.csv
Minimal:
- pharmacy_minimal_{scenario}_v5.csv

Usage
-----
python pharmacy_data_generator_v5.py --out_dir . --days 365 --start_date 2025-11-05 --seed 42

Dependencies: numpy, pandas
"""

from __future__ import annotations

import argparse
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd


# -----------------------------
# Defaults / Constants
# -----------------------------
TZ_OFFSET = "+05:30"
MERCHANT_ID = "m_pharmacy_001"

DEFAULT_START_DATE = "2025-11-05"
DEFAULT_DAYS = 365
DEFAULT_SEED = 42

SCENARIOS = ("base", "stress", "fraud_like")

# Diversified channels
CHANNEL_UPI = "UPI"
CHANNEL_CARD = "CARD"
CHANNEL_BANK = "BANK"
CHANNEL_NET_BANKING = "NET_BANKING"
CHANNEL_WALLET = "WALLET"
CHANNEL_COD_SETTLEMENT = "COD_SETTLEMENT"

# EPHEMERAL categories/notes (synthetic, non-identifying)
CUSTOMER_TAGS = ["Medical", "Pharmacy", "Health"]
SUPPLIER_TAGS = ["Wholesale", "Distributor", "Inventory"]
TRANSFER_TAGS = ["Money Transfer", "Self Transfer"]
PLATFORM_TAGS = ["Settlement", "Cashback", "Fee"]
CONDITIONAL_TAGS = ["Reimbursement", "Claim"]

# Counterparty token pools (synthetic, stable, non-identifying; EPHEMERAL ONLY)
N_CUSTOMERS = 900
N_CHRONIC = 75
SUPPLIERS = ["cp_supplier_001", "cp_supplier_002", "cp_supplier_003", "cp_supplier_004"]
UTILITIES = ["cp_utility_electricity", "cp_utility_telecom", "cp_utility_rent"]
PLATFORMS = ["cp_platform_paytm", "cp_platform_phonepe", "cp_platform_bank"]
OWNER = "cp_owner_001"

# Negative testing knobs (Paytm-like only; ingestion must DROP these)
FAIL_RATE_INSUFFICIENT_FUNDS = 0.004   # 0.4% of debit attempts
FAIL_RATE_TIMEOUT = 0.003              # 0.3% of attempts
FAIL_RATE_NETWORK = 0.002              # 0.2% of attempts
INVALID_TOKEN_RATE = 0.006             # 0.6% (only when token present)
PARTIAL_RECORD_RATE = 0.004            # 0.4% (simulated truncated optional fields)

RECORD_STATUS_SUCCESS = "SUCCESS"
RECORD_STATUS_FAIL_INSUFF = "FAILED_INSUFFICIENT_FUNDS"
RECORD_STATUS_FAIL_TIMEOUT = "FAILED_TIMEOUT"
RECORD_STATUS_FAIL_NETWORK = "FAILED_NETWORK"
RECORD_STATUS_INVALID_TOKEN = "INVALID_TOKEN"

# Chronic refill behavior (EPHEMERAL-only via token usage)
REFILL_CYCLE_DAYS = (26, 34)        # jitter around 30-day refill cadence
CHRONIC_REFILL_PROB = 0.55          # chance refill occurs when due-window hit
CHRONIC_REFILL_AMOUNT = (250, 1400)

MISS_RATE_BASE = 0.10
MISS_RATE_STRESS = 0.35
MISS_RATE_FRAUD = 0.08

LATE_REFILL_PROB_STRESS = 0.40
LATE_REFILL_DELAY_DAYS = (5, 18)


# -----------------------------
# Utilities
# -----------------------------
def parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def iso_ts(d: datetime, t: time, tz: str) -> str:
    return datetime.combine(d.date(), t).strftime(f"%Y-%m-%dT%H:%M:%S{tz}")


def sample_times(n: int) -> List[time]:
    """
    Pharmacy time-of-day: peaks in late morning (9-14) and evening (17-22).
    """
    out: List[time] = []
    for _ in range(n):
        r = random.random()
        if r < 0.45:  # evening peak
            hour = int(np.clip(np.random.normal(19.3, 1.0), 17, 22))
            minute = int(np.clip(np.random.normal(18, 16), 0, 59))
        elif r < 0.75:  # late morning peak
            hour = int(np.clip(np.random.normal(11.2, 0.9), 9, 14))
            minute = int(np.clip(np.random.normal(22, 18), 0, 59))
        else:  # uniform spread
            hour = random.randint(9, 22)
            minute = random.randint(0, 59)
        second = random.randint(0, 59)
        out.append(time(hour, minute, second))
    out.sort()
    return out


def seasonal_multiplier(d: datetime) -> float:
    """
    Simple seasonality for pharmacy:
    - Winter (Nov–Feb): higher demand
    - Monsoon (Jul–Sep): slightly higher
    - Summer (Apr–Jun): baseline/slightly lower
    """
    m = d.month
    if m in (11, 12, 1, 2):
        return 1.18
    if m in (7, 8, 9):
        return 1.08
    if m in (4, 5, 6):
        return 0.95
    return 1.00


def volume_mu(d: datetime, scenario: str) -> int:
    """
    Baseline daily retail txn count with:
    - weekend uplift
    - month-start uplift
    - seasonal multiplier
    - scenario modifier
    """
    weekend = d.weekday() >= 5
    dom = d.day
    base = 70 + (10 if weekend else 0) + (12 if dom <= 5 else 0)
    base = int(base * seasonal_multiplier(d))

    if scenario == "stress":
        base = int(base * 0.68)
    elif scenario == "fraud_like":
        base = int(base * 1.07)

    return base


def pick_channel_for_retail(n: int, fraud_like: bool) -> List[str]:
    """
    Retail customer receipts:
    - UPI dominates
    - some CARD
    - some WALLET
    - BANK rare
    """
    if fraud_like:
        probs = {CHANNEL_UPI: 0.78, CHANNEL_CARD: 0.12, CHANNEL_WALLET: 0.08, CHANNEL_BANK: 0.02}
    else:
        probs = {CHANNEL_UPI: 0.64, CHANNEL_CARD: 0.22, CHANNEL_WALLET: 0.12, CHANNEL_BANK: 0.02}

    ch = list(probs.keys())
    p = np.array(list(probs.values()), dtype=float)
    p = p / p.sum()
    return list(np.random.choice(ch, size=n, p=p))


def gen_credit_amounts(n: int, fraud_like: bool) -> List[float]:
    """
    Mixture distribution: small OTC + medium Rx + rare high ticket.
    Fraud-like: more round amounts.
    """
    amts: List[float] = []
    for _ in range(n):
        r = random.random()
        if r < 0.60:
            a = np.random.lognormal(mean=math.log(240), sigma=0.55)
        elif r < 0.95:
            a = np.random.lognormal(mean=math.log(720), sigma=0.45)
        else:
            a = np.random.lognormal(mean=math.log(2600), sigma=0.35)

        if fraud_like and random.random() < 0.55:
            a = round(a / 50) * 50

        amts.append(round(float(a), 2))
    return amts


# -----------------------------
# Counterparty Tokens (EPHEMERAL ONLY)
# -----------------------------
CUSTOMERS = [f"cp_customer_{i:04d}" for i in range(1, N_CUSTOMERS + 1)]
CHRONIC = CUSTOMERS[:N_CHRONIC]

_zipf_ranks = np.arange(1, N_CHRONIC + 1)
_zipf_weights = 1 / (_zipf_ranks ** 1.15)
_zipf_weights = _zipf_weights / _zipf_weights.sum()


def sample_customer_token() -> str:
    """
    55% from chronic pool (repeat behavior), 45% from long tail.
    """
    if random.random() < 0.55:
        return str(np.random.choice(CHRONIC, p=_zipf_weights))
    return random.choice(CUSTOMERS[N_CHRONIC:])


def sample_supplier_token() -> str:
    probs = np.array([0.45, 0.30, 0.18, 0.07], dtype=float)
    return str(np.random.choice(SUPPLIERS, p=probs))


def sample_platform_token() -> str:
    probs = np.array([0.65, 0.20, 0.15], dtype=float)  # Paytm > PhonePe > bank
    return str(np.random.choice(PLATFORMS, p=probs))


def sample_utility_token(kind: str) -> str:
    mapping = {
        "rent": "cp_utility_rent",
        "electricity": "cp_utility_electricity",
        "telecom": "cp_utility_telecom",
    }
    return mapping.get(kind, random.choice(UTILITIES))


# -----------------------------
# Negative testing injection (Paytm-like only; drop in ingestion)
# -----------------------------
def maybe_inject_failure(
    amount: float,
    direction: str,
    channel: str,
    raw_counterparty_token: str,
) -> Tuple[str, str, int, float, str]:
    """
    Returns: (record_status, failure_reason, partial_record, amount_out, token_out)

    Rules:
    - Failed transactions should NOT affect underwriting features: ingestion should ignore non-SUCCESS.
    - Partial records simulate parsing/transport truncation in optional fields.
    - Invalid token simulates a token not belonging to known pools.
    """
    # Insufficient funds mostly relevant for debits
    if direction == "debit" and random.random() < FAIL_RATE_INSUFFICIENT_FUNDS:
        return (RECORD_STATUS_FAIL_INSUFF, "insufficient_funds", 0, amount, raw_counterparty_token)

    if random.random() < FAIL_RATE_TIMEOUT:
        partial = 1 if random.random() < 0.7 else 0
        return (RECORD_STATUS_FAIL_TIMEOUT, "timeout", partial, amount, raw_counterparty_token)

    if random.random() < FAIL_RATE_NETWORK:
        partial = 1 if random.random() < 0.6 else 0
        return (RECORD_STATUS_FAIL_NETWORK, "network_failure", partial, amount, raw_counterparty_token)

    if raw_counterparty_token and random.random() < INVALID_TOKEN_RATE:
        bad = f"cp_invalid_{random.randint(100000, 999999)}"
        return (RECORD_STATUS_INVALID_TOKEN, "unknown_counterparty_token", 0, amount, bad)

    if random.random() < PARTIAL_RECORD_RATE:
        return (RECORD_STATUS_SUCCESS, "partial_record", 1, amount, raw_counterparty_token)

    return (RECORD_STATUS_SUCCESS, "", 0, amount, raw_counterparty_token)


# -----------------------------
# Chronic refill modeling (EPHEMERAL tokens only)
# -----------------------------
def init_chronic_refill_state(start_date: datetime, chronic_tokens: List[str]) -> Dict[str, datetime]:
    """
    Next due date per chronic token. Purely internal state during generation.
    """
    state: Dict[str, datetime] = {}
    for tok in chronic_tokens:
        first_due = start_date + timedelta(days=random.randint(0, 20))
        state[tok] = first_due
    return state


def emit_chronic_refills_for_day(
    d: datetime,
    scenario: str,
    refill_state: Dict[str, datetime],
) -> List[Tuple[str, float, str]]:
    """
    Returns list of (counterparty_token, amount, channel) for refill purchases on day d.
    """
    if scenario == "stress":
        miss_rate = MISS_RATE_STRESS
    elif scenario == "fraud_like":
        miss_rate = MISS_RATE_FRAUD
    else:
        miss_rate = MISS_RATE_BASE

    out: List[Tuple[str, float, str]] = []
    for tok, due in list(refill_state.items()):
        # due-window: +/- 2 days around due date
        if abs((d.date() - due.date()).days) <= 2:
            # miss?
            if random.random() < miss_rate:
                # stress: some become late refills (catch-up)
                if scenario == "stress" and random.random() < LATE_REFILL_PROB_STRESS:
                    delay = random.randint(*LATE_REFILL_DELAY_DAYS)
                    refill_state[tok] = due + timedelta(days=delay)
                else:
                    # skip cycle -> push to next cycle
                    refill_state[tok] = due + timedelta(days=random.randint(*REFILL_CYCLE_DAYS))
                continue

            # refill occurs with some probability
            if random.random() > CHRONIC_REFILL_PROB:
                refill_state[tok] = due + timedelta(days=random.randint(*REFILL_CYCLE_DAYS))
                continue

            amt = round(float(np.random.uniform(*CHRONIC_REFILL_AMOUNT)), 2)
            ch = str(np.random.choice([CHANNEL_UPI, CHANNEL_CARD, CHANNEL_WALLET], p=[0.62, 0.28, 0.10]))
            out.append((tok, amt, ch))

            refill_state[tok] = due + timedelta(days=random.randint(*REFILL_CYCLE_DAYS))

    return out


# -----------------------------
# Core generation
# -----------------------------
PAYTM_LIKE_COLUMNS = [
    "merchant_id",
    "ts",
    "amount",
    "direction",
    "channel",
    "raw_category",            # EPHEMERAL ONLY
    "raw_note",                # EPHEMERAL ONLY
    "raw_counterparty_token",  # EPHEMERAL ONLY
    "role_hint",               # EPHEMERAL ONLY (test ground truth)
    "purpose_hint",            # EPHEMERAL ONLY (test ground truth)
    "cct_hint",                # EPHEMERAL ONLY (test ground truth)
    "record_status",           # EPHEMERAL ONLY (negative testing)
    "failure_reason",          # EPHEMERAL ONLY
    "partial_record",          # EPHEMERAL ONLY
]

MINIMAL_COLUMNS = ["merchant_id", "ts", "amount", "direction", "channel"]


def generate_day(
    d: datetime,
    scenario: str,
    refill_state: Dict[str, datetime],
) -> List[List[str]]:
    """
    Returns Paytm-like rows with ephemeral context + hints + failure fields.
    """
    fraud_like = scenario == "fraud_like"
    mu = volume_mu(d, scenario)
    credit_n = int(np.clip(np.random.normal(mu, 10), 30, 170))

    rows: List[List[str]] = []

    # 0) Explicit chronic refill purchases (adds realistic cadence + misses/late)
    refill_purchases = emit_chronic_refills_for_day(d, scenario, refill_state)
    refill_times = sample_times(len(refill_purchases)) if refill_purchases else []
    for (tok, amt, ch), t in zip(refill_purchases, refill_times):
        direction = "credit"
        role, purpose, cct = "customer", "sale", "FREE"
        cat, note = "Pharmacy", "Refill"

        record_status, failure_reason, partial_record, amt_out, tok_out = maybe_inject_failure(
            amount=float(amt),
            direction=direction,
            channel=ch,
            raw_counterparty_token=tok,
        )
        amt = amt_out
        tok = tok_out

        if partial_record == 1:
            if random.random() < 0.7:
                note = ""
            if random.random() < 0.4:
                cat = ""

        ts = iso_ts(d, t, TZ_OFFSET)
        rows.append([
            MERCHANT_ID, ts, f"{amt:.2f}", direction, ch,
            cat, note, tok,
            role, purpose, cct,
            record_status, failure_reason, partial_record
        ])

    # 1) Generic retail receipts
    times = sample_times(credit_n)
    amts = gen_credit_amounts(credit_n, fraud_like=fraud_like)
    retail_channels = pick_channel_for_retail(credit_n, fraud_like=fraud_like)

    for t, amt, ch in zip(times, amts, retail_channels):
        direction = "credit"
        r = random.random()

        # Retail sale -> FREE
        if r < 0.84:
            role, purpose, cct = "customer", "sale", "FREE"
            cat, note = random.choice(CUSTOMER_TAGS), "Purchase"
            cp = sample_customer_token()

        # Platform settlement -> PASS_THROUGH (includes WALLET + COD_SETTLEMENT)
        elif r < 0.92:
            role, purpose, cct = "platform", "settlement", "PASS_THROUGH"
            cp = sample_platform_token()
            cat, note = "Settlement", "Settlement"
            amt = round(amt * np.random.uniform(2.2, 4.0), 2)

            sr = random.random()
            if sr < 0.55:
                ch = CHANNEL_BANK
                note = "Settlement (bank)"
            elif sr < 0.80:
                ch = CHANNEL_WALLET
                note = "Settlement (wallet)"
            else:
                ch = CHANNEL_COD_SETTLEMENT
                note = "COD settlement"

        # Owner infusion -> ARTIFICIAL
        elif r < 0.985:
            role, purpose, cct = "owner", "owner_transfer", "ARTIFICIAL"
            cat, note = random.choice(TRANSFER_TAGS), "Transfer"
            cp = OWNER
            ch = CHANNEL_BANK if random.random() < 0.7 else CHANNEL_UPI
            amt = round(float(np.random.lognormal(mean=math.log(45000), sigma=0.35)), 2)

        # Conditional reimbursements -> CONDITIONAL
        else:
            role, purpose, cct = "platform", "reimbursement", "CONDITIONAL"
            cat, note = random.choice(CONDITIONAL_TAGS), "Reimbursement"
            cp = "cp_conditional_001"
            ch = CHANNEL_BANK
            amt = round(float(np.random.lognormal(mean=math.log(6000), sigma=0.30)), 2)

        record_status, failure_reason, partial_record, amt_out, cp_out = maybe_inject_failure(
            amount=float(amt),
            direction=direction,
            channel=ch,
            raw_counterparty_token=cp,
        )
        amt = amt_out
        cp = cp_out

        if partial_record == 1:
            if random.random() < 0.7:
                note = ""
            if random.random() < 0.4:
                cat = ""

        ts = iso_ts(d, t, TZ_OFFSET)
        rows.append([
            MERCHANT_ID, ts, f"{amt:.2f}", direction, ch,
            cat, note, cp,
            role, purpose, cct,
            record_status, failure_reason, partial_record
        ])

    # 2) Debits: supplier + ops + fees + owner withdraw + refunds
    debits: List[Tuple[str, float, str, str, str, str, str, str]] = []
    # tuple: (channel, amt, cat, note, cp, role, purpose, cct)

    # Weekly inventory purchase (Tue): NET_BANKING bias
    if d.weekday() == 1:
        amt = round(float(np.random.lognormal(mean=math.log(38000), sigma=0.25)), 2)
        ch = CHANNEL_NET_BANKING if random.random() < 0.65 else CHANNEL_BANK
        debits.append((ch, amt, random.choice(SUPPLIER_TAGS), "Inventory purchase",
                       sample_supplier_token(), "supplier", "inventory", "CONSTRAINED"))

    # Monthly rent (5th): BANK
    if d.day == 5:
        amt = round(float(np.random.lognormal(mean=math.log(28000), sigma=0.20)), 2)
        debits.append((CHANNEL_BANK, amt, "Rent", "Shop rent",
                       sample_utility_token("rent"), "utility", "operating_expense", "CONSTRAINED"))

    # Utilities (10th, 20th)
    if d.day in (10, 20):
        amt = round(float(np.random.lognormal(mean=math.log(6500), sigma=0.18)), 2)
        util_kind = "electricity" if random.random() < 0.6 else "telecom"
        debits.append((CHANNEL_BANK, amt, "Utilities", "Bills",
                       sample_utility_token(util_kind), "utility", "operating_expense", "CONSTRAINED"))

    # Platform fees: BANK/WALLET/CARD mix (PASS_THROUGH)
    if random.random() < 0.30:
        amt = round(float(np.random.uniform(15, 250)), 2)
        ch = str(np.random.choice([CHANNEL_BANK, CHANNEL_WALLET, CHANNEL_CARD], p=[0.55, 0.25, 0.20]))
        debits.append((ch, amt, "Fee", "Charges",
                       sample_platform_token(), "platform", "fee", "PASS_THROUGH"))

    # Owner withdraw: UPI/WALLET (ARTIFICIAL)
    if random.random() < (0.08 if scenario != "stress" else 0.05):
        amt = round(float(np.random.lognormal(mean=math.log(4000), sigma=0.35)), 2)
        ch = CHANNEL_UPI if random.random() < 0.75 else CHANNEL_WALLET
        debits.append((ch, amt, "Money Transfer", "Owner withdraw",
                       OWNER, "owner", "owner_transfer", "ARTIFICIAL"))

    # Refunds: UPI/WALLET (PASS_THROUGH)
    if random.random() < 0.01:
        amt = round(float(np.random.lognormal(mean=math.log(500), sigma=0.45)), 2)
        ch = CHANNEL_UPI if random.random() < 0.7 else CHANNEL_WALLET
        debits.append((ch, amt, "Refund", "Refund",
                       sample_customer_token(), "customer", "refund", "PASS_THROUGH"))

    # Stress: emergency stock purchase (CONSTRAINED) NET_BANKING/BANK
    if scenario == "stress" and random.random() < 0.35:
        amt = round(float(np.random.lognormal(mean=math.log(12000), sigma=0.25)), 2)
        ch = CHANNEL_NET_BANKING if random.random() < 0.55 else CHANNEL_BANK
        debits.append((ch, amt, random.choice(SUPPLIER_TAGS), "Emergency stock",
                       sample_supplier_token(), "supplier", "inventory", "CONSTRAINED"))

    # Fraud-like: extra chargeback/fee (PASS_THROUGH) CARD
    if scenario == "fraud_like" and random.random() < 0.40:
        amt = round(float(np.random.uniform(200, 1200)), 2)
        debits.append((CHANNEL_CARD, amt, "Fee", "Chargeback fee",
                       sample_platform_token(), "platform", "fee", "PASS_THROUGH"))

    # Render debit rows with failure injection + partial record simulation
    for ch, amt, cat, note, cp, role, purpose, cct in debits:
        direction = "debit"
        t = time(random.choice([8, 9, 22, 23]), random.randint(0, 59), random.randint(0, 59))

        record_status, failure_reason, partial_record, amt_out, cp_out = maybe_inject_failure(
            amount=float(amt),
            direction=direction,
            channel=ch,
            raw_counterparty_token=cp,
        )
        amt = amt_out
        cp = cp_out

        if partial_record == 1:
            if random.random() < 0.7:
                note = ""
            if random.random() < 0.4:
                cat = ""

        ts = iso_ts(d, t, TZ_OFFSET)
        rows.append([
            MERCHANT_ID, ts, f"{amt:.2f}", direction, ch,
            cat, note, cp,
            role, purpose, cct,
            record_status, failure_reason, partial_record
        ])

    return rows


def generate_dataset(
    scenario: str,
    start_date: datetime,
    days: int,
) -> pd.DataFrame:
    refill_state = init_chronic_refill_state(start_date, CHRONIC)

    all_rows: List[List[str]] = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        all_rows.extend(generate_day(d, scenario=scenario, refill_state=refill_state))

    df = pd.DataFrame(all_rows, columns=PAYTM_LIKE_COLUMNS)
    # sort stable
    df["ts_sort"] = pd.to_datetime(df["ts"].str.replace(TZ_OFFSET, ""), errors="coerce")
    df = df.sort_values("ts_sort").drop(columns=["ts_sort"]).reset_index(drop=True)
    return df


def minimal_export(df: pd.DataFrame) -> pd.DataFrame:
    return df[MINIMAL_COLUMNS].copy()


def write_outputs(out_dir: str, start_date: datetime, days: int, seed: int) -> None:
    set_seeds(seed)

    for scenario in SCENARIOS:
        df = generate_dataset(scenario=scenario, start_date=start_date, days=days)

        paytm_like_path = f"{out_dir}/pharmacy_paytm_like_{scenario}_v5.csv"
        minimal_path = f"{out_dir}/pharmacy_minimal_{scenario}_v5.csv"

        df.to_csv(paytm_like_path, index=False)
        minimal_export(df).to_csv(minimal_path, index=False)


# -----------------------------
# CLI
# -----------------------------
def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate synthetic pharmacy transactions (v5).")
    p.add_argument("--out_dir", type=str, default=".", help="Output directory for CSV files.")
    p.add_argument("--start_date", type=str, default=DEFAULT_START_DATE, help="YYYY-MM-DD")
    p.add_argument("--days", type=int, default=DEFAULT_DAYS, help="Number of days to generate.")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Random seed.")
    return p


def main() -> None:
    args = build_arg_parser().parse_args()
    start_date = parse_date(args.start_date)
    write_outputs(out_dir=args.out_dir, start_date=start_date, days=args.days, seed=args.seed)


if __name__ == "__main__":
    main()
