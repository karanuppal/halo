from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "halo_get_draft.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "mock")
    monkeypatch.setenv("HALO_LLM_PROVIDER", "fake")

    from services.api.app.main import app

    with TestClient(app) as c:
        yield c


def test_get_draft_returns_card(client: TestClient) -> None:
    created = client.post(
        "/v1/command",
        json={"household_id": "hh-1", "user_id": "u-1", "raw_command_text": "reorder usual"},
    )
    assert created.status_code == 200
    created_card = created.json()

    draft_id = created_card["draft_id"]
    response = client.get(f"/v1/drafts/{draft_id}")
    assert response.status_code == 200

    card = response.json()
    assert card["type"] == "DRAFT"
    assert card["draft_id"] == draft_id
    assert card["title"].startswith("Draft:")


def test_get_draft_not_found(client: TestClient) -> None:
    response = client.get("/v1/drafts/does-not-exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Draft not found"
