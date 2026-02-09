from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "halo_audit.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "mock")
    monkeypatch.setenv("HALO_LLM_PROVIDER", "fake")

    from services.api.app.main import app

    with TestClient(app) as c:
        yield c


def test_audit_endpoints_return_execution_and_receipt(client: TestClient) -> None:
    draft = client.post(
        "/v1/command",
        json={"household_id": "hh-1", "user_id": "u-1", "raw_command_text": "reorder usual"},
    ).json()
    draft_id = draft["draft_id"]

    done = client.post("/v1/draft/confirm", json={"draft_id": draft_id, "user_id": "u-1"}).json()
    execution_id = done["execution_id"]

    lst = client.get("/v1/executions", params={"household_id": "hh-1"})
    assert lst.status_code == 200
    rows = lst.json()
    assert rows, "Expected executions in activity feed"
    assert any(r["execution_id"] == execution_id for r in rows)

    detail = client.get(f"/v1/executions/{execution_id}")
    assert detail.status_code == 200
    d = detail.json()
    assert d["execution_id"] == execution_id
    assert d["raw_command_text"]
    assert d["receipts"], "Expected receipt artifacts in detail"

    receipts = client.get(f"/v1/receipts/{execution_id}")
    assert receipts.status_code == 200
    rs = receipts.json()
    assert rs
    assert rs[0]["type"] in {"ORDER_RECEIPT", "CANCEL_CONFIRMATION", "BOOKING_CONFIRMATION"}
