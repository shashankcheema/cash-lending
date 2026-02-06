"""
Pharmacy Synthetic Data Generator (v2 — Cash Control Realism)
Language: Python

Generates Paytm-like transaction CSVs for a single pharmacy MSME with:
- Minimal RBI-safe upload schema: merchant_id, ts, amount, direction, channel
- Optional ephemeral fields for classifier dev: raw_category, raw_note
- Optional ground-truth hints for testing only: role_hint, purpose_hint, cct_hint

Scenarios:
- base
- stress
- fraud_like

Date range (default): 2025-11-05 to 2026-02-04 (92 days)
Timezone offset: +05:30

IMPORTANT COMPLIANCE NOTE:
- This generator includes optional 'raw_category/raw_note' + hint fields ONLY for testing.
- In production ingestion, these fields must be processed ephemerally and NEVER stored/logged.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


# -----------------------------
# Config
# -----------------------------
TZ_OFFSET = "+05:30"
MERCHANT_ID = "m_pharmacy_001"

DEFAULT_START_DATE = datetime(2025, 11, 5)
DEFAULT_DAYS = 92  # 2025-11-05 to 2026-02-04 inclusive-ish

RANDOM_SEED = 42

# Ephemeral-like categories / notes (synthetic, non-identifying)
CUSTOMER_TAGS = ["Medical", "Pharmacy", "Health"]
SUPPLIER_TAGS = ["Wholesale", "Distributor", "Inventory"]
OPEX_TAGS = ["Utilities", "Rent", "Fuel", "Telecom"]
TRANSFER_TAGS = ["Money Transfer", "Self Transfer"]
PLATFORM_TAGS = ["Settlement", "Cashback", "Fee"]
CONDITIONAL_TAGS = ["Reimbursement", "Claim"]


# -----------------------------
# Helpers
# -----------------------------
def _set_seeds(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


def _iso_ts(d: datetime, t: time, tz: str) -> str:
    return datetime.combine(d.date(), t).strftime(f"%Y-%m-%dT%H:%M:%S{tz}")


def _sample_times(n: int) -> List[time]:
    """
    Pharmacy time-of-day: peaks in late morning (9-14) and evening (17-22),
    with some uniform spread.
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
        else:  # uniform
            hour = random.randint(9, 22)
            minute = random.randint(0, 59)
        second = random.randint(0, 59)
        out.append(time(hour, minute, second))
    out.sort()
    return out


def _pick_channel(n: int, fraud_like: bool) -> List[str]:
    """
    Channel mix: UPI heavy, some card, some bank.
    Fraud-like: slightly more UPI, more skew.
    """
    probs = {"UPI": 0.84, "CARD": 0.11, "BANK": 0.05} if fraud_like else {"UPI": 0.72, "CARD": 0.20, "BANK": 0.08}
    ch = list(probs.keys())
    p = np.array(list(probs.values()))
    p = p / p.sum()
    return list(np.random.choice(ch, size=n, p=p))


def _gen_credit_amounts(n: int, fraud_like: bool) -> List[float]:
    """
    Mixture distribution: small OTC + medium Rx + rare high ticket.
    Fraud-like: more round amounts.
    """
    amts: List[float] = []
    for _ in range(n):
        r = random.random()
        if r < 0.60:
            a = np.random.lognormal(mean=math.log(240), sigma=0.55)    # small
        elif r < 0.95:
            a = np.random.lognormal(mean=math.log(720), sigma=0.45)    # medium
        else:
            a = np.random.lognormal(mean=math.log(2600), sigma=0.35)   # rare high

        if fraud_like and random.random() < 0.55:
            a = round(a / 50) * 50  # round dominance

        amts.append(round(float(a), 2))
    return amts


def _volume_mu(d: datetime, scenario: str) -> int:
    """
    Baseline volume with weekend + month-start uplift.
    Stress: reduce volume.
    Fraud-like: slightly increase volume and add bursty effects via rounding.
    """
    weekend = d.weekday() >= 5
    dom = d.day  # day of month
    mu = 70 + (10 if weekend else 0) + (12 if dom <= 5 else 0)

    if scenario == "stress":
        mu = int(mu * 0.68)
    elif scenario == "fraud_like":
        mu = int(mu * 1.07)

    return mu


# -----------------------------
# Core generation
# -----------------------------
def generate_pharmacy_day(d: datetime, scenario: str) -> List[List[str]]:
    """
    Returns a list of rows with columns:
    merchant_id, ts, amount, direction, channel, raw_category, raw_note, role_hint, purpose_hint, cct_hint
    """
    fraud_like = scenario == "fraud_like"
    mu = _volume_mu(d, scenario)
    credit_n = int(np.clip(np.random.normal(mu, 10), 30, 150))

    times = _sample_times(credit_n)
    amts = _gen_credit_amounts(credit_n, fraud_like=fraud_like)
    channels = _pick_channel(credit_n, fraud_like=fraud_like)

    rows: List[List[str]] = []

    # ---- Credits ----
    # Most are retail sales (FREE), some settlements (PASS_THROUGH), some owner infusions (ARTIFICIAL), rare conditional
    for t, amt, ch in zip(times, amts, channels):
        r = random.random()
        if r < 0.86:
            role, purpose, cct = "customer", "sale", "FREE"
            cat, note = random.choice(CUSTOMER_TAGS), "Purchase"
        elif r < 0.93:
            role, purpose, cct = "platform", "settlement", "PASS_THROUGH"
            cat, note = random.choice(PLATFORM_TAGS), "Settlement"
            amt = round(amt * np.random.uniform(2.2, 4.0), 2)  # settlement-like
        elif r < 0.985:
            role, purpose, cct = "owner", "owner_transfer", "ARTIFICIAL"
            cat, note = random.choice(TRANSFER_TAGS), "Transfer"
            amt = round(float(np.random.lognormal(mean=math.log(45000), sigma=0.35)), 2)
        else:
            role, purpose, cct = "platform", "reimbursement", "CONDITIONAL"
            cat, note = random.choice(CONDITIONAL_TAGS), "Reimbursement"
            amt = round(float(np.random.lognormal(mean=math.log(6000), sigma=0.30)), 2)

        ts = _iso_ts(d, t, TZ_OFFSET)
        rows.append([MERCHANT_ID, ts, f"{amt:.2f}", "credit", ch, cat, note, role, purpose, cct])

    # ---- Debits ----
    debits: List[Tuple[str, float, str, str, str, str, str]] = []

    # Weekly inventory purchase (Tue)
    if d.weekday() == 1:
        amt = round(float(np.random.lognormal(mean=math.log(38000), sigma=0.25)), 2)
        debits.append(("BANK", amt, random.choice(SUPPLIER_TAGS), "Inventory purchase", "supplier", "inventory", "CONSTRAINED"))

    # Monthly rent (5th)
    if d.day == 5:
        amt = round(float(np.random.lognormal(mean=math.log(28000), sigma=0.20)), 2)
        debits.append(("BANK", amt, "Rent", "Shop rent", "utility", "operating_expense", "CONSTRAINED"))

    # Utilities (10th, 20th)
    if d.day in (10, 20):
        amt = round(float(np.random.lognormal(mean=math.log(6500), sigma=0.18)), 2)
        debits.append(("BANK", amt, "Utilities", "Bills", "utility", "operating_expense", "CONSTRAINED"))

    # Platform fees small & frequent
    if random.random() < 0.28:
        amt = round(float(np.random.uniform(15, 250)), 2)
        debits.append(("BANK", amt, "Fee", "Charges", "platform", "fee", "PASS_THROUGH"))

    # Owner personal withdrawal (rare)
    if random.random() < (0.08 if scenario != "stress" else 0.05):
        amt = round(float(np.random.lognormal(mean=math.log(4000), sigma=0.35)), 2)
        debits.append(("UPI", amt, "Money Transfer", "Owner withdraw", "owner", "owner_transfer", "ARTIFICIAL"))

    # Refunds (rare)
    if random.random() < 0.01:
        amt = round(float(np.random.lognormal(mean=math.log(500), sigma=0.45)), 2)
        debits.append(("UPI", amt, "Refund", "Refund", "customer", "refund", "PASS_THROUGH"))

    # Stress: emergency stock purchases
    if scenario == "stress" and random.random() < 0.35:
        amt = round(float(np.random.lognormal(mean=math.log(12000), sigma=0.25)), 2)
        debits.append(("BANK", amt, random.choice(SUPPLIER_TAGS), "Emergency stock", "supplier", "inventory", "CONSTRAINED"))

    # Fraud-like: extra platform fee/chargeback style debits
    if scenario == "fraud_like" and random.random() < 0.40:
        amt = round(float(np.random.uniform(200, 1200)), 2)
        debits.append(("CARD", amt, "Fee", "Chargeback fee", "platform", "fee", "PASS_THROUGH"))

    # Debit timestamps (morning/late)
    for ch, amt, cat, note, role, purpose, cct in debits:
        t = time(random.choice([8, 9, 22, 23]), random.randint(0, 59), random.randint(0, 59))
        ts = _iso_ts(d, t, TZ_OFFSET)
        rows.append([MERCHANT_ID, ts, f"{amt:.2f}", "debit", ch, cat, note, role, purpose, cct])

    return rows


def generate_pharmacy_dataset(
    scenario: str = "base",
    start_date: datetime = DEFAULT_START_DATE,
    days: int = DEFAULT_DAYS,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """
    Returns a DataFrame with Paytm-like columns + hint columns (for testing only).
    """
    _set_seeds(seed)
    all_rows: List[List[str]] = []
    for i in range(days):
        d = start_date + timedelta(days=i)
        all_rows.extend(generate_pharmacy_day(d, scenario=scenario))

    df = pd.DataFrame(
        all_rows,
        columns=[
            "merchant_id",
            "ts",
            "amount",
            "direction",
            "channel",
            "raw_category",
            "raw_note",
            "role_hint",
            "purpose_hint",
            "cct_hint",
        ],
    )
    df["ts_sort"] = pd.to_datetime(df["ts"].str.replace(TZ_OFFSET, ""), errors="coerce")
    df = df.sort_values("ts_sort").drop(columns=["ts_sort"]).reset_index(drop=True)
    return df


def write_outputs(
    out_dir: str = ".",
    start_date: datetime = DEFAULT_START_DATE,
    days: int = DEFAULT_DAYS,
    seed: int = RANDOM_SEED,
) -> Dict[str, str]:
    """
    Writes:
    - Paytm-like (ephemeral columns + hints)
    - Minimal RBI-safe (merchant_id, ts, amount, direction, channel)
    """
    outputs: Dict[str, str] = {}

    scenarios = ["base", "stress", "fraud_like"]
    for sc in scenarios:
        df = generate_pharmacy_dataset(sc, start_date=start_date, days=days, seed=seed)

        paytm_like_path = f"{out_dir}/pharmacy_paytm_like_{sc}_05Nov25_04Feb26.csv"
        df.to_csv(paytm_like_path, index=False)
        outputs[f"paytm_like_{sc}"] = paytm_like_path

        minimal_df = df[["merchant_id", "ts", "amount", "direction", "channel"]].copy()
        minimal_path = f"{out_dir}/pharmacy_minimal_{sc}_05Nov25_04Feb26.csv"
        minimal_df.to_csv(minimal_path, index=False)
        outputs[f"minimal_{sc}"] = minimal_path

    return outputs


if __name__ == "__main__":
    # Example usage:
    # python pharmacy_data_generator.py
    out = write_outputs(out_dir=".")
    print("Generated files:")
    for k, v in out.items():
        print(f" - {k}: {v}")
