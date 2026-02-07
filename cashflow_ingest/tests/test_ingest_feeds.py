from fastapi.testclient import TestClient

from cashflow_ingest.api.app import app


def _post_feed(client: TestClient, payload: dict):
    return client.post("/v1/ingest/feeds", json=payload)


def test_feed_ingest_success():
    client = TestClient(app)
    payload = {
        "subject_ref": "m1",
        "source": "PAYTM",
        "watermark_ts": "2025-01-02T00:00:00+05:30",
        "events": [
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": 100,
                "direction": "credit",
                "channel": "UPI",
            },
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T01:00:00+05:30",
                "amount": 50,
                "direction": "debit",
                "channel": "BANK",
            },
        ],
    }
    resp = _post_feed(client, payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_accepted"] == 2
    assert body["rows_rejected"] == 0
    assert body["watermark_ts"].startswith("2025-01-02")


def test_feed_missing_watermark_rejected():
    client = TestClient(app)
    payload = {
        "subject_ref": "m1",
        "source": "PAYTM",
        "events": [
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": 100,
                "direction": "credit",
                "channel": "UPI",
            }
        ],
    }
    resp = _post_feed(client, payload)
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "missing watermark_ts"


def test_feed_missing_watermark_allowed_in_dev(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("ALLOW_MISSING_WATERMARK", "1")
    payload = {
        "subject_ref": "m1",
        "source": "PAYTM",
        "allow_missing_watermark": True,
        "events": [
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": 100,
                "direction": "credit",
                "channel": "UPI",
            }
        ],
    }
    resp = _post_feed(client, payload)
    assert resp.status_code == 200
    assert "watermark_ts" in resp.json()


def test_feed_replay_duplicate_409():
    client = TestClient(app)
    payload = {
        "subject_ref": "m1",
        "source": "PAYTM",
        "watermark_ts": "2025-01-02T00:00:00+05:30",
        "events": [
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": 100,
                "direction": "credit",
                "channel": "UPI",
            }
        ],
    }
    first = _post_feed(client, payload)
    assert first.status_code == 200
    second = _post_feed(client, payload)
    assert second.status_code == 409


def test_feed_invalid_rows_rejected_and_counted():
    client = TestClient(app)
    payload = {
        "subject_ref": "m1",
        "source": "PAYTM",
        "watermark_ts": "2025-01-02T00:00:00+05:30",
        "events": [
            {
                "merchant_id": "m1",
                "ts": "not-a-date",
                "amount": 100,
                "direction": "credit",
                "channel": "UPI",
            },
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T00:00:00+05:30",
                "amount": -5,
                "direction": "credit",
                "channel": "UPI",
            },
            {
                "merchant_id": "m1",
                "ts": "2025-01-01T01:00:00+05:30",
                "amount": 10,
                "direction": "credit",
                "channel": "UPI",
            },
        ],
    }
    resp = _post_feed(client, payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_accepted"] == 1
    assert body["rows_rejected"] == 2
    assert body["rejection_breakdown"]["INVALID_TS"] == 1
    assert body["rejection_breakdown"]["INVALID_AMOUNT"] == 1
