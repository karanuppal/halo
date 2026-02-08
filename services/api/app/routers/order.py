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
from services.api.app.services.amazon_mock import AmazonMockAdapter
from services.api.app.services.store import DraftRecord, store


router = APIRouter()
adapter = AmazonMockAdapter()


@router.post("/v1/order/draft", response_model=OrderDraftResponse)
def create_order_draft(payload: OrderDraftRequest) -> OrderDraftResponse:
    draft_id = uuid4().hex
    draft = adapter.build_draft(payload.items)

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

    execution_id = uuid4().hex
    result = adapter.execute(record.response.estimated_total_cents)

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
