from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    db_path = tmp_path / "halo_resy_err.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")
    monkeypatch.setenv("HALO_LLM_PROVIDER", "fake")
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "mock")

    # Force Resy adapter for booking.
    monkeypatch.setenv("HALO_BOOKING_ADAPTER", "resy")

    # Keep Resy storage_state isolated per test.
    monkeypatch.setenv("HALO_RESY_STORAGE_STATE_DIR", str(tmp_path / "resy_sessions"))

    from services.api.app.main import app

    with TestClient(app) as c:
        yield c


def test_book_with_resy_requires_linked_session(client: TestClient) -> None:
    resp = client.post(
        "/v1/command",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": "book dinner tomorrow",
        },
    )
    assert resp.status_code == 412
    assert "Booking session not linked" in resp.json().get("detail", "")


def test_book_with_resy_requires_venue_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange: create a fake linked session file so we get past the link check.
    sessions = tmp_path / "resy_sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    (sessions / "hh-1.json").write_text("{}", encoding="utf-8")

    db_path = tmp_path / "halo_resy_err2.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    monkeypatch.setenv("HALO_DB_AUTO_CREATE", "true")
    monkeypatch.setenv("HALO_LLM_PROVIDER", "fake")
    monkeypatch.setenv("HALO_AMAZON_ADAPTER", "mock")
    monkeypatch.setenv("HALO_BOOKING_ADAPTER", "resy")
    monkeypatch.setenv("HALO_RESY_STORAGE_STATE_DIR", str(sessions))

    # Intentionally do NOT set HALO_RESY_VENUE_URL.
    monkeypatch.delenv("HALO_RESY_VENUE_URL", raising=False)

    from services.api.app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/v1/command",
            json={
                "household_id": "hh-1",
                "user_id": "u-1",
                "raw_command_text": "book dinner tomorrow",
            },
        )

    assert resp.status_code == 502
    assert "HALO_RESY_VENUE_URL" in resp.json().get("detail", "")
