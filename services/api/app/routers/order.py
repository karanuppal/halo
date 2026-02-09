from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException
from services.api.app.models.order import (
    OrderConfirmRequest,
    OrderConfirmResponse,
    OrderDraftRequest,
    OrderDraftResponse,
    OrderReceipt,
)
from services.api.app.services.amazon_base import (
    AmazonAdapterError,
    AmazonBotCheckError,
    AmazonCheckoutTotalDriftError,
    AmazonLinkRequiredError,
    AmazonPlaywrightMissingError,
)
from services.api.app.services.amazon_factory import get_amazon_adapter
from services.api.app.services.store import DraftRecord, store

router = APIRouter()


def _raise_adapter_http_error(e: Exception) -> None:
    if isinstance(e, AmazonLinkRequiredError):
        raise HTTPException(status_code=412, detail=str(e)) from e

    if isinstance(e, AmazonPlaywrightMissingError):
        raise HTTPException(status_code=503, detail=str(e)) from e

    if isinstance(e, AmazonCheckoutTotalDriftError):
        raise HTTPException(status_code=409, detail=str(e)) from e

    if isinstance(e, AmazonBotCheckError):
        raise HTTPException(status_code=502, detail=str(e)) from e

    if isinstance(e, AmazonAdapterError):
        raise HTTPException(status_code=502, detail=str(e)) from e

    raise HTTPException(status_code=500, detail="Internal Server Error") from e


@router.post("/v1/order/draft", response_model=OrderDraftResponse)
def create_order_draft(payload: OrderDraftRequest) -> OrderDraftResponse:
    try:
        adapter = get_amazon_adapter()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    draft_id = uuid4().hex
    try:
        draft = adapter.build_draft(payload.household_id, payload.items)
    except Exception as e:
        _raise_adapter_http_error(e)

    response = OrderDraftResponse(
        draft_id=draft_id,
        verb="ORDER",
        vendor=adapter.vendor,
        items=draft.items,
        estimated_total_cents=draft.estimated_total_cents,
        delivery_window=draft.delivery_window,
        payment_method_masked=draft.payment_method_masked,
        warnings=draft.warnings,
    )

    store.save_draft(DraftRecord(request=payload, response=response))
    return response


@router.post("/v1/order/confirm", response_model=OrderConfirmResponse)
def confirm_order(payload: OrderConfirmRequest) -> OrderConfirmResponse:
    record = store.get_draft(payload.draft_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    try:
        adapter = get_amazon_adapter()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if record.response.vendor != adapter.vendor:
        raise HTTPException(
            status_code=409,
            detail="Draft vendor does not match current adapter configuration",
        )

    execution_id = uuid4().hex
    try:
        result = adapter.execute(
            household_id=record.request.household_id,
            items=record.response.items,
            expected_total_cents=record.response.estimated_total_cents,
        )
    except Exception as e:
        _raise_adapter_http_error(e)

    return OrderConfirmResponse(
        execution_id=execution_id,
        status="DONE",
        receipt=OrderReceipt(
            receipt_id=result.receipt_id,
            provider=adapter.vendor,
            total_cents=result.total_cents,
            summary=result.summary,
        ),
    )
