from fastapi.testclient import TestClient
from services.api.app.main import app

client = TestClient(app)


def test_parse_reorder_usual_returns_intent() -> None:
    resp = client.post(
        "/v1/command/parse",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": "reorder the usual",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verb"] == "REORDER"
    assert data["routine_key"].startswith("REORDER")
    assert data["confidence"] > 0


def test_parse_cancel_requires_subscription_name_or_clarification() -> None:
    resp = client.post(
        "/v1/command/parse",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": "cancel",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verb"] == "CANCEL_SUBSCRIPTION"
    assert data["clarifications"], "Expected bounded clarification questions"
    assert len(data["clarifications"]) <= 2


def test_parse_cancel_with_answer_resolves_subscription() -> None:
    resp = client.post(
        "/v1/command/parse",
        json={
            "household_id": "hh-1",
            "user_id": "u-1",
            "raw_command_text": "cancel",
            "clarification_answers": {"q0": "Netflix"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verb"] == "CANCEL_SUBSCRIPTION"
    assert data["params"]["subscription_name"] == "Netflix"
    assert data["clarifications"] == []
