from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "halo_cmd.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "mock")
    monkeypatch.setenv("HALO_LLM_PROVIDER", "fake")

    from services.api.app.main import app

    with TestClient(app) as c:
        yield c


def test_command_reorder_returns_draft_card(client: TestClient) -> None:
    resp = client.post(
        "/v1/command",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": "reorder the usual",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["type"] == "DRAFT"
    assert data["draft_id"]
    assert data["vendor"] == "AMAZON_MOCK"
    assert data["estimated_cost_cents"] and data["estimated_cost_cents"] > 0

    actions = [a["type"] for a in data["actions"]]
    assert actions == ["CONFIRM", "MODIFY", "CANCEL"]


def test_command_cancel_netflix_returns_draft_card(client: TestClient) -> None:
    resp = client.post(
        "/v1/command",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": "cancel netflix",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["type"] == "DRAFT"
    assert data["draft_id"]
    assert data["vendor"] == "MOCK_SUBS"
    assert data["title"].startswith("Draft: CANCEL")
    assert data["body"]["name"] == "Netflix"
    assert data["warnings"], "Expected irreversibility warning"


def test_command_book_cleaning_returns_draft_card(client: TestClient) -> None:
    resp = client.post(
        "/v1/command",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": "book cleaner next week",
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["type"] == "DRAFT"
    assert data["draft_id"]
    assert data["vendor"] == "MOCK_BOOKING"
    assert data["body"]["service_type"]
    assert len(data["body"]["time_windows"]) == 3
