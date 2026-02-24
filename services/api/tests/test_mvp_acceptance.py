from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "halo_acceptance.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "mock")
    monkeypatch.setenv("HALO_BOOKING_ADAPTER", "mock")
    monkeypatch.setenv("HALO_LLM_PROVIDER", "fake")

    from services.api.app.main import app

    with TestClient(app) as c:
        yield c


def _submit_command(client: TestClient, text: str) -> dict:
    resp = client.post(
        "/v1/command",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": text,
            "channel": "IMESSAGE",
        },
    )
    assert resp.status_code == 200
    return resp.json()


def _confirm(client: TestClient, draft_id: str) -> dict:
    resp = client.post("/v1/draft/confirm", json={"draft_id": draft_id, "user_id": "u-1"})
    assert resp.status_code == 200
    return resp.json()


def test_mvp_acceptance_reorder_flow(client: TestClient) -> None:
    draft = _submit_command(client, "order paper towels")

    assert draft["type"] == "DRAFT"
    assert draft["title"] == "Draft: REORDER"
    assert draft["estimated_cost_cents"] > 0
    assert draft["body"]["items"]
    assert draft["body"]["delivery_window"]
    assert draft["body"]["payment_method_masked"]

    done = _confirm(client, draft["draft_id"])
    assert done["type"] == "DONE"
    assert done["title"] == "Done: REORDER"

    execution_id = done["execution_id"]
    receipts = client.get(f"/v1/receipts/{execution_id}")
    assert receipts.status_code == 200
    receipt_rows = receipts.json()
    assert receipt_rows
    assert receipt_rows[0]["type"] == "ORDER_RECEIPT"

    executions = client.get("/v1/executions", params={"household_id": "hh-1"})
    assert executions.status_code == 200
    listed = executions.json()
    assert any(row["execution_id"] == execution_id and row["status"] == "DONE" for row in listed)


def test_mvp_acceptance_cancel_flow(client: TestClient) -> None:
    draft = _submit_command(client, "cancel netflix")

    assert draft["type"] == "DRAFT"
    assert draft["title"] == "Draft: CANCEL SUBSCRIPTION"
    assert draft["body"]["name"] == "Netflix"
    assert draft["warnings"]

    done = _confirm(client, draft["draft_id"])
    assert done["type"] == "DONE"
    assert done["title"] == "Done: CANCEL SUBSCRIPTION"

    execution_id = done["execution_id"]
    receipts = client.get(f"/v1/receipts/{execution_id}")
    assert receipts.status_code == 200
    receipt_rows = receipts.json()
    assert receipt_rows
    assert receipt_rows[0]["type"] == "CANCEL_CONFIRMATION"


def test_mvp_acceptance_book_flow_with_modify(client: TestClient) -> None:
    draft = _submit_command(client, "book cleaner next week")

    assert draft["type"] == "DRAFT"
    assert draft["title"] == "Draft: BOOK APPOINTMENT"
    assert len(draft["body"]["time_windows"]) == 3

    modified = client.post(
        "/v1/draft/modify",
        json={"draft_id": draft["draft_id"], "modifications": {"selected_time_window_index": 1}},
    )
    assert modified.status_code == 200
    modified_card = modified.json()
    assert modified_card["type"] == "DRAFT"
    assert modified_card["body"]["selected_time_window_index"] == 1

    done = _confirm(client, draft["draft_id"])
    assert done["type"] == "DONE"
    assert done["title"] == "Done: BOOK APPOINTMENT"

    execution_id = done["execution_id"]
    detail = client.get(f"/v1/executions/{execution_id}")
    assert detail.status_code == 200
    payload = detail.json()["execution_payload_json"]
    assert payload["details"]["time_window"] == modified_card["body"]["time_windows"][1]

    receipts = client.get(f"/v1/receipts/{execution_id}")
    assert receipts.status_code == 200
    receipt_rows = receipts.json()
    assert receipt_rows
    assert receipt_rows[0]["type"] == "BOOKING_CONFIRMATION"


def test_mvp_acceptance_unsupported_flow(client: TestClient) -> None:
    unsupported = _submit_command(client, "fix kitchen sink")

    assert unsupported["type"] == "UNSUPPORTED"
    assert unsupported["body"]["supported"] == [
        "REORDER",
        "CANCEL_SUBSCRIPTION",
        "BOOK_APPOINTMENT",
    ]
