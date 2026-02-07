from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Dict, Iterable, Tuple

from cashflow_ingest.api.schemas import CanonicalTxn


def compute_daily_inflow_outflow(events: Iterable[CanonicalTxn]) -> Dict[date, Tuple[float, float]]:
    """
    Derived-only aggregate:
    returns {day: (inflow_total, outflow_total)} computed in-memory.

    Notes:
    - This uses only CanonicalTxn objects, so it's already "required columns only".
    - If/when you add Paytm-like failure fields, filter those BEFORE building CanonicalTxn.
    """
    buckets: Dict[date, list[float]] = defaultdict(lambda: [0.0, 0.0])

    for e in events:
        d = e.event_ts.date()
        if e.direction.value == "credit":
            buckets[d][0] += float(e.amount)
        else:
            buckets[d][1] += float(e.amount)

    return {d: (vals[0], vals[1]) for d, vals in buckets.items()}
