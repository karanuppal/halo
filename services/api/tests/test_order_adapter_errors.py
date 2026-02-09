from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from services.api.app.main import app
from services.api.app.services.amazon_base import (
    AmazonAdapterError,
    AmazonBotCheckError,
    AmazonCheckoutTotalDriftError,
    AmazonLinkRequiredError,
    AmazonPlaywrightMissingError,
)

client = TestClient(app)


class _RaisingAdapter:
    vendor = "AMAZON_BROWSER"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def build_draft(self, household_id: str, items: list[object]) -> object:
        del household_id, items
        raise self._exc

    def execute(
        self,
        household_id: str,
        items: list[object],
        expected_total_cents: int,
    ) -> object:
        del household_id, items, expected_total_cents
        raise self._exc


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (AmazonLinkRequiredError(Path("/tmp/state.json")), 412),
        (AmazonPlaywrightMissingError(), 503),
        (AmazonBotCheckError(Path("/tmp/artifact.png")), 502),
        (
            AmazonCheckoutTotalDriftError(expected_total_cents=1000, actual_total_cents=2000),
            409,
        ),
        (AmazonAdapterError("boom"), 502),
    ],
)
def test_order_draft_maps_adapter_errors(
    monkeypatch: pytest.MonkeyPatch,
    exc: Exception,
    status: int,
) -> None:
    import services.api.app.routers.order as order_router

    monkeypatch.setattr(order_router, "get_amazon_adapter", lambda: _RaisingAdapter(exc))

    payload = {
        "household_id": "hh-1",
        "user_id": "u-1",
        "items": [{"name": "paper towels", "quantity": 1}],
    }

    response = client.post("/v1/order/draft", json=payload)
    assert response.status_code == status
    assert "detail" in response.json()


def test_order_draft_unknown_error_is_500(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.api.app.routers.order as order_router

    monkeypatch.setattr(order_router, "get_amazon_adapter", lambda: _RaisingAdapter(Exception("x")))

    payload = {
        "household_id": "hh-1",
        "user_id": "u-1",
        "items": [{"name": "paper towels", "quantity": 1}],
    }

    response = client.post("/v1/order/draft", json=payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Server Error"
