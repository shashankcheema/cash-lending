import os

from cashflow_ingest.ingest.pipeline.cct_classifier import classify_cct
from cashflow_ingest.ingest.pipeline.cct_enums import CCT
from cashflow_ingest.ingest.pipeline.semantic_classifier import TxnSemantic


def _sem(raw_narration: str | None) -> TxnSemantic:
    return TxnSemantic(
        subject_ref="s1",
        event_ts=None,
        direction="credit",
        amount=100.0,
        channel="UPI",
        raw_category=None,
        raw_narration=raw_narration,
        raw_counterparty_token=None,
        role_class="UNKNOWN",
        purpose_class="UNKNOWN",
    )


def test_ambiguity_returns_unknown(monkeypatch):
    # Ensure defaults
    monkeypatch.delenv("AMBIGUITY_DELTA", raising=False)
    monkeypatch.delenv("MIN_CCT_CONFIDENCE", raising=False)

    # narration contains both settlement and owner markers -> two hard rules same confidence
    sem = _sem("settlement owner transfer")
    res = classify_cct(sem)
    assert res.cct == CCT.UNKNOWN


def test_threshold_forces_unknown(monkeypatch):
    monkeypatch.setenv("MIN_CCT_CONFIDENCE", "0.95")
    sem = _sem("sale")
    res = classify_cct(sem)
    assert res.cct == CCT.UNKNOWN
