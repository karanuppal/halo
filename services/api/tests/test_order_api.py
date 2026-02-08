from fastapi.testclient import TestClient
from services.api.app.main import app

client = TestClient(app)


def test_create_order_draft_returns_expected_fields() -> None:
    payload = {
        "household_id": "hh-1",
        "user_id": "u-1",
        "items": [{"name": "paper towels", "quantity": 2}],
    }
    response = client.post("/v1/order/draft", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["verb"] == "ORDER"
    assert data["vendor"] == "AMAZON_MOCK"
    assert data["estimated_total_cents"] > 0
    assert data["payment_method_masked"].startswith("Visa")
    assert isinstance(data["items"], list)
    assert data["items"][0]["name"] == "paper towels"


def test_create_order_draft_validates_items() -> None:
    payload = {
        "household_id": "hh-1",
        "user_id": "u-1",
        "items": [],
    }
    response = client.post("/v1/order/draft", json=payload)
    assert response.status_code == 422


def test_confirm_requires_existing_draft() -> None:
    response = client.post("/v1/order/confirm", json={"draft_id": "missing"})
    assert response.status_code == 404


def test_confirm_executes_and_returns_receipt() -> None:
    payload = {
        "household_id": "hh-1",
        "user_id": "u-1",
        "items": [{"name": "detergent", "quantity": 1}],
    }
    draft_response = client.post("/v1/order/draft", json=payload)
    draft_id = draft_response.json()["draft_id"]

    confirm_response = client.post("/v1/order/confirm", json={"draft_id": draft_id})
    assert confirm_response.status_code == 200

    data = confirm_response.json()
    assert data["status"] == "DONE"
    assert "receipt" in data
    assert data["receipt"]["total_cents"] > 0
