from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, Iterable

from cashflow_ingest.api.schemas import CanonicalTxn
from cashflow_ingest.ingest.pipeline.cct_classifier import classify_cct
from cashflow_ingest.ingest.pipeline.cct_enums import CCT
from cashflow_ingest.ingest.pipeline.semantic_classifier import classify_role_purpose


def _bucket_key(cct: CCT, direction: str) -> str:
    direction = direction.lower()
    suffix = "IN" if direction == "credit" else "OUT"
    return f"{cct.value}_{suffix}"


def aggregate_daily_control(events: Iterable[CanonicalTxn]) -> dict[str, dict]:
    """
    Build daily control aggregates:
    returns dict keyed by day string YYYY-MM-DD.
    """
    counts: dict[date, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    sums: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    unique_tokens: dict[date, set[str]] = defaultdict(set)
    partial_counts: dict[date, int] = defaultdict(int)
    unknown_counts: dict[date, int] = defaultdict(int)

    for e in events:
        d = e.event_ts.date()
        sem = classify_role_purpose(e)
        cct = classify_cct(sem)
        if cct.cct == CCT.UNKNOWN:
            unknown_counts[d] += 1

        bucket = _bucket_key(cct.cct, sem.direction)
        counts[d][bucket] += 1
        sums[d][bucket] += float(e.amount)

        if e.raw_counterparty_token:
            unique_tokens[d].add(e.raw_counterparty_token)

        if e.partial_record:
            partial_counts[d] += 1

    result: dict[str, dict] = {}
    for d in sorted(counts.keys()):
        day_str = d.isoformat()
        counts_day = counts[d]
        sums_day = sums[d]

        # Ensure all buckets exist
        for cct in CCT:
            for suffix in ("IN", "OUT"):
                key = f"{cct.value}_{suffix}"
                counts_day.setdefault(key, 0)
                sums_day.setdefault(key, 0.0)

        total_in = sum(v for k, v in sums_day.items() if k.endswith("_IN"))
        total_out = sum(v for k, v in sums_day.items() if k.endswith("_OUT"))
        total_flow = total_in + total_out

        free_in = sums_day["FREE_IN"]
        free_out = sums_day["FREE_OUT"]
        free_cash_net = free_in - free_out

        owner_dependency_ratio = sums_day["ARTIFICIAL_IN"] / max(1e-9, total_in)
        pass_through_ratio = (sums_day["PASS_THROUGH_IN"] + sums_day["PASS_THROUGH_OUT"]) / max(1e-9, total_flow)
        unknown_flow_ratio = (sums_day["UNKNOWN_IN"] + sums_day["UNKNOWN_OUT"]) / max(1e-9, total_flow)

        result[day_str] = {
            "day": day_str,
            "counts": dict(counts_day),
            "sums": {k: round(v, 2) for k, v in sums_day.items()},
            "derived": {
                "free_cash_net": round(free_cash_net, 2),
                "owner_dependency_ratio": round(owner_dependency_ratio, 6),
                "pass_through_ratio": round(pass_through_ratio, 6),
                "unknown_flow_ratio": round(unknown_flow_ratio, 6),
                "unique_payers_count": len(unique_tokens[d]),
                "accepted_partial_rows": partial_counts[d],
                "unknown_cct_count": unknown_counts[d],
            },
        }

    return result
