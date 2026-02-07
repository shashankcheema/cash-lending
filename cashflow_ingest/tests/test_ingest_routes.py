from fastapi.testclient import TestClient

from cashflow_ingest.api.app import app


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _post_csv(client: TestClient, csv_text: str, *, subject_ref: str = "m1", source: str = "PAYTM"):
    files = {"file": ("test.csv", _csv_bytes(csv_text), "text/csv")}
    data = {"subject_ref": subject_ref, "source": source}
    return client.post("/v1/ingest/files", data=data, files=files)


def test_ingest_success_with_status_and_partial():
    client = TestClient(app)
    csv = (
        "merchant_id,ts,amount,direction,channel,record_status,partial_record\n"
        "m1,2025-01-01T00:00:00+05:30,100,credit,UPI,SUCCESS,1\n"
        "m1,2025-01-01T01:00:00+05:30,50,debit,BANK,FAILED_TIMEOUT,0\n"
        "m1,2025-01-01T02:00:00+05:30,25,credit,UPI,SUCCESS,true\n"
    )
    resp = _post_csv(client, csv)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_accepted"] == 2
    assert body["rows_rejected"] == 1
    assert body["rejection_breakdown"] == {"FAILED_TIMEOUT": 1}
    assert body["accepted_partial_rows"] == 2


def test_ingest_unknown_status_bucketed():
    client = TestClient(app)
    csv = (
        "merchant_id,ts,amount,direction,channel,record_status\n"
        "m1,2025-01-01T00:00:00+05:30,100,credit,UPI,PARTIAL_RECORD\n"
        "m1,2025-01-01T01:00:00+05:30,50,credit,UPI,SUCCESS\n"
    )
    resp = _post_csv(client, csv)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_accepted"] == 1
    assert body["rows_rejected"] == 1
    assert body["rejection_breakdown"] == {"UNKNOWN_STATUS": 1}


def test_ingest_invalid_rows_rejected_and_counted():
    client = TestClient(app)
    csv = (
        "merchant_id,ts,amount,direction,channel\n"
        "m1,not-a-date,100,credit,UPI\n"
        "m1,2025-01-01T00:00:00+05:30,-10,credit,UPI\n"
        "m1,2025-01-01T01:00:00+05:30,10,credit,UPI\n"
    )
    resp = _post_csv(client, csv)
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows_accepted"] == 1
    assert body["rows_rejected"] == 2
    assert body["rejection_breakdown"]["INVALID_TS"] == 1
    assert body["rejection_breakdown"]["INVALID_AMOUNT"] == 1


def test_ingest_all_rows_invalid_returns_400():
    client = TestClient(app)
    csv = (
        "merchant_id,ts,amount,direction,channel\n"
        "m1,not-a-date,100,credit,UPI\n"
    )
    resp = _post_csv(client, csv)
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"] == "no valid rows after filtering/validation"
    assert body["detail"]["rows_accepted"] == 0


def test_ingest_empty_batch_returns_400():
    client = TestClient(app)
    csv = "merchant_id,ts,amount,direction,channel\n"
    resp = _post_csv(client, csv)
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"] == "empty batch"


def test_min_accept_ratio_guard(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("MIN_ACCEPT_RATIO", "0.9")
    csv = (
        "merchant_id,ts,amount,direction,channel\n"
        "m1,not-a-date,100,credit,UPI\n"
        "m1,not-a-date,100,credit,UPI\n"
        "m1,not-a-date,100,credit,UPI\n"
        "m1,2025-01-01T00:00:00+05:30,10,credit,UPI\n"
    )
    resp = _post_csv(client, csv)
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["error"] == "accepted_ratio below minimum threshold"


def test_min_accept_ratio_disabled(monkeypatch):
    client = TestClient(app)
    monkeypatch.setenv("MIN_ACCEPT_RATIO", "0")
    csv = (
        "merchant_id,ts,amount,direction,channel\n"
        "m1,not-a-date,100,credit,UPI\n"
        "m1,2025-01-01T00:00:00+05:30,10,credit,UPI\n"
    )
    resp = _post_csv(client, csv)
    assert resp.status_code == 200
