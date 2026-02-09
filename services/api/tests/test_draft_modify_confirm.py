from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "halo_confirm.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "mock")
    monkeypatch.setenv("HALO_LLM_PROVIDER", "fake")

    from services.api.app.main import app

    with TestClient(app) as c:
        yield c


def test_reorder_confirm_returns_done(client: TestClient) -> None:
    draft_card = client.post(
        "/v1/command",
        json={"household_id": "hh-1", "user_id": "u-1", "raw_command_text": "reorder usual"},
    ).json()
    draft_id = draft_card["draft_id"]

    done = client.post("/v1/draft/confirm", json={"draft_id": draft_id, "user_id": "u-1"})
    assert done.status_code == 200

    data = done.json()
    assert data["type"] == "DONE"
    assert data["execution_id"]
    assert data["vendor"] == "AMAZON_MOCK"
    assert data["body"]["receipt_id"]


def test_cancel_confirm_returns_done(client: TestClient) -> None:
    draft_card = client.post(
        "/v1/command",
        json={"household_id": "hh-1", "user_id": "u-1", "raw_command_text": "cancel netflix"},
    ).json()
    draft_id = draft_card["draft_id"]

    done = client.post("/v1/draft/confirm", json={"draft_id": draft_id, "user_id": "u-1"})
    assert done.status_code == 200

    data = done.json()
    assert data["type"] == "DONE"
    assert data["execution_id"]
    assert "confirmation_id" in data["body"]


def test_book_modify_selects_option_2_then_confirm(client: TestClient) -> None:
    draft_card = client.post(
        "/v1/command",
        json={"household_id": "hh-1", "user_id": "u-1", "raw_command_text": "book cleaner"},
    ).json()
    draft_id = draft_card["draft_id"]

    modified = client.post(
        "/v1/draft/modify",
        json={"draft_id": draft_id, "modifications": {"selected_time_window_index": 1}},
    )
    assert modified.status_code == 200

    m = modified.json()
    assert m["type"] == "DRAFT"
    assert m["body"]["selected_time_window_index"] == 1

    done = client.post("/v1/draft/confirm", json={"draft_id": draft_id, "user_id": "u-1"})
    assert done.status_code == 200

    data = done.json()
    assert data["type"] == "DONE"
    assert data["execution_id"]
    assert "confirmation_id" in data["body"]
