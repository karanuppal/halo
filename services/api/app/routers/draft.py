from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from packages.shared.schemas.card_v1 import (
    CardActionTypeV1,
    CardActionV1,
    CardTypeV1,
    CardV1,
)
from services.api.app.db.deps import get_db
from services.api.app.db.models import (
    Confirmation,
    Draft,
    EventLog,
    Execution,
    ExecutionRequest,
    ReceiptArtifact,
)
from services.api.app.models.draft import DraftConfirmRequest, DraftModifyRequest
from services.api.app.models.order import OrderItemInput, OrderItemPriced
from services.api.app.services.amazon_base import (
    AmazonAdapterError,
    AmazonBotCheckError,
    AmazonCheckoutTotalDriftError,
    AmazonLinkRequiredError,
    AmazonPlaywrightMissingError,
)
from services.api.app.services.amazon_factory import get_amazon_adapter
from services.api.app.services.booking_base import (
    BookingAdapterError,
    BookingLinkRequiredError,
    BookingPlaywrightMissingError,
)
from services.api.app.services.booking_factory import get_booking_adapter
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/v1/draft/modify", response_model=CardV1)
def modify_draft(payload: DraftModifyRequest, db: Session = Depends(get_db)) -> CardV1:
    draft = db.get(Draft, payload.draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    if draft.verb == "REORDER":
        return _modify_reorder(db, draft, payload.modifications)

    if draft.verb == "CANCEL_SUBSCRIPTION":
        return _modify_cancel_subscription(db, draft, payload.modifications)

    if draft.verb == "BOOK_APPOINTMENT":
        return _modify_book_appointment(db, draft, payload.modifications)

    raise HTTPException(status_code=409, detail=f"Unknown draft verb: {draft.verb}")


@router.post("/v1/draft/confirm", response_model=CardV1)
def confirm_draft(payload: DraftConfirmRequest, db: Session = Depends(get_db)) -> CardV1:
    draft = db.get(Draft, payload.draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    household_id, request_user_id = _draft_context(db, draft)

    now = datetime.utcnow()
    latency_ms = 0
    if getattr(draft, "created_at", None) is not None:
        latency_ms = int((now - draft.created_at).total_seconds() * 1000)

    confirmation_id = uuid4().hex
    db.add(
        Confirmation(
            id=confirmation_id,
            draft_id=draft.id,
            user_id=payload.user_id,
            confirmation_latency_ms=max(0, latency_ms),
        )
    )

    execution_id = uuid4().hex
    execution = Execution(
        id=execution_id,
        draft_id=draft.id,
        status="IN_PROGRESS",
        finished_at=None,
        final_cost_cents=None,
        execution_payload_json={},
        error_message=None,
    )
    db.add(execution)

    _log_event(
        db,
        household_id=household_id,
        user_id=payload.user_id,
        entity_type="Draft",
        entity_id=draft.id,
        event_type="DRAFT_CONFIRMED",
        event_payload={"confirmation_id": confirmation_id, "latency_ms": latency_ms},
    )
    _log_event(
        db,
        household_id=household_id,
        user_id=payload.user_id,
        entity_type="Execution",
        entity_id=execution_id,
        event_type="EXECUTION_STARTED",
        event_payload={"draft_id": draft.id, "verb": draft.verb},
    )

    db.commit()

    try:
        if draft.verb == "REORDER":
            done = _execute_reorder(db, draft, execution)
        elif draft.verb == "CANCEL_SUBSCRIPTION":
            done = _execute_cancel_subscription(db, draft, execution)
        elif draft.verb == "BOOK_APPOINTMENT":
            done = _execute_book_appointment(db, draft, execution)
        else:
            raise HTTPException(status_code=409, detail=f"Unknown draft verb: {draft.verb}")

        done.household_id = household_id
        done.user_id = payload.user_id or request_user_id
        return done
    except HTTPException:
        raise
    except Exception as e:
        execution.status = "FAILED"
        execution.finished_at = datetime.utcnow()
        execution.error_message = str(e)
        execution.execution_payload_json = {"error": str(e)}

        _log_event(
            db,
            household_id=household_id,
            user_id=payload.user_id,
            entity_type="Execution",
            entity_id=execution.id,
            event_type="EXECUTION_FAILED",
            event_payload={"error": str(e)},
        )
        db.commit()

        return CardV1(
            type=CardTypeV1.FAILED,
            title=f"Failed: {draft.verb}",
            summary=str(e),
            household_id=household_id,
            user_id=payload.user_id or request_user_id,
            draft_id=draft.id,
            execution_id=execution.id,
            vendor=draft.vendor,
            estimated_cost_cents=draft.estimated_cost_cents,
            body={"error": str(e)},
            actions=[
                CardActionV1(type=CardActionTypeV1.RETRY, label="Retry", payload={}),
            ],
            warnings=[],
        )


def _modify_reorder(db: Session, draft: Draft, modifications: dict) -> CardV1:
    household_id, request_user_id = _draft_context(db, draft)

    try:
        adapter = get_amazon_adapter()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if draft.vendor != adapter.vendor:
        raise HTTPException(status_code=409, detail="Draft vendor mismatch")

    raw_items = modifications.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return _draft_to_card(db, draft, household_id, request_user_id)

    items: list[OrderItemInput] = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        qty = int(it.get("quantity") or 1)
        if not name:
            continue
        items.append(OrderItemInput(name=name, quantity=max(1, qty)))

    if not items:
        return _draft_to_card(db, draft, household_id, request_user_id)

    try:
        draft_result = adapter.build_draft(household_id, items)
    except Exception as e:
        _raise_adapter_http_error(e)

    draft.estimated_cost_cents = draft_result.estimated_total_cents
    payload = dict(draft.draft_payload_json or {})
    payload.update(
        {
            "items": [i.model_dump(mode="json") for i in draft_result.items],
            "estimated_total_cents": draft_result.estimated_total_cents,
            "delivery_window": draft_result.delivery_window,
            "payment_method_masked": draft_result.payment_method_masked,
            "warnings": draft_result.warnings,
        }
    )
    draft.draft_payload_json = payload

    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="Draft",
        entity_id=draft.id,
        event_type="DRAFT_MODIFIED",
        event_payload={"modifications": modifications},
    )

    db.commit()
    return _draft_to_card(db, draft, household_id, request_user_id)


def _modify_cancel_subscription(db: Session, draft: Draft, modifications: dict) -> CardV1:
    household_id, request_user_id = _draft_context(db, draft)

    payload = dict(draft.draft_payload_json or {})
    sub = payload.get("subscription") or {}

    new_name = str(modifications.get("subscription_name") or "").strip()
    new_id = str(modifications.get("subscription_id") or "").strip()

    if not new_name and not new_id:
        return _draft_to_card(db, draft, household_id, request_user_id)

    if new_name:
        sub["name"] = new_name
    if new_id:
        sub["id"] = new_id

    payload["subscription"] = sub
    draft.draft_payload_json = payload

    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="Draft",
        entity_id=draft.id,
        event_type="DRAFT_MODIFIED",
        event_payload={"modifications": modifications},
    )

    db.commit()
    return _draft_to_card(db, draft, household_id, request_user_id)


def _modify_book_appointment(db: Session, draft: Draft, modifications: dict) -> CardV1:
    household_id, request_user_id = _draft_context(db, draft)

    payload = dict(draft.draft_payload_json or {})
    idx = modifications.get("selected_time_window_index")

    if isinstance(idx, int) and idx in {0, 1, 2}:
        payload["selected_time_window_index"] = idx
        draft.draft_payload_json = payload

        _log_event(
            db,
            household_id=household_id,
            user_id=request_user_id,
            entity_type="Draft",
            entity_id=draft.id,
            event_type="DRAFT_MODIFIED",
            event_payload={"modifications": modifications},
        )
        db.commit()

    return _draft_to_card(db, draft, household_id, request_user_id)


def _execute_reorder(db: Session, draft: Draft, execution: Execution) -> CardV1:
    household_id, request_user_id = _draft_context(db, draft)

    try:
        adapter = get_amazon_adapter()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if draft.vendor != adapter.vendor:
        raise HTTPException(status_code=409, detail="Draft vendor mismatch")

    payload = draft.draft_payload_json or {}
    raw_items = payload.get("items")

    if not isinstance(raw_items, list) or not raw_items:
        raise HTTPException(status_code=409, detail="Draft missing items")

    items: list[OrderItemPriced] = [OrderItemPriced.model_validate(it) for it in raw_items]
    expected_total = int(draft.estimated_cost_cents or 0)

    try:
        result = adapter.execute(
            household_id=household_id,
            items=items,
            expected_total_cents=expected_total,
        )
    except Exception as e:
        _raise_adapter_http_error(e)

    execution.status = "DONE"
    execution.finished_at = datetime.utcnow()
    execution.final_cost_cents = result.total_cents
    execution.execution_payload_json = {
        "receipt_id": result.receipt_id,
        "summary": result.summary,
        "total_cents": result.total_cents,
    }

    receipt_row_id = uuid4().hex
    db.add(
        ReceiptArtifact(
            id=receipt_row_id,
            execution_id=execution.id,
            type="ORDER_RECEIPT",
            content_text=result.summary,
            external_reference_id=result.receipt_id,
        )
    )

    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="Execution",
        entity_id=execution.id,
        event_type="EXECUTION_DONE",
        event_payload=execution.execution_payload_json,
    )
    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="ReceiptArtifact",
        entity_id=receipt_row_id,
        event_type="RECEIPT_CREATED",
        event_payload={"type": "ORDER_RECEIPT", "external_reference_id": result.receipt_id},
    )

    db.commit()

    return CardV1(
        type=CardTypeV1.DONE,
        title="Done: REORDER",
        summary=f"Receipt: {result.receipt_id}",
        household_id=household_id,
        user_id=request_user_id,
        draft_id=draft.id,
        execution_id=execution.id,
        vendor=draft.vendor,
        estimated_cost_cents=result.total_cents,
        body={
            "receipt_id": result.receipt_id,
            "summary": result.summary,
            "total_cents": result.total_cents,
        },
        actions=[],
        warnings=[],
    )


def _execute_cancel_subscription(db: Session, draft: Draft, execution: Execution) -> CardV1:
    household_id, request_user_id = _draft_context(db, draft)

    payload = draft.draft_payload_json or {}
    sub = payload.get("subscription") or {}

    name = str(sub.get("name") or "subscription")

    confirmation_id = f"cancel_{uuid4().hex[:10]}"
    content = f"Cancellation confirmed for {name}. Confirmation: {confirmation_id}"

    execution.status = "DONE"
    execution.finished_at = datetime.utcnow()
    execution.final_cost_cents = None
    execution.execution_payload_json = {
        "confirmation_id": confirmation_id,
        "subscription": sub,
    }

    receipt_row_id = uuid4().hex
    db.add(
        ReceiptArtifact(
            id=receipt_row_id,
            execution_id=execution.id,
            type="CANCEL_CONFIRMATION",
            content_text=content,
            external_reference_id=confirmation_id,
        )
    )

    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="Execution",
        entity_id=execution.id,
        event_type="EXECUTION_DONE",
        event_payload=execution.execution_payload_json,
    )
    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="ReceiptArtifact",
        entity_id=receipt_row_id,
        event_type="RECEIPT_CREATED",
        event_payload={"type": "CANCEL_CONFIRMATION", "external_reference_id": confirmation_id},
    )

    db.commit()

    return CardV1(
        type=CardTypeV1.DONE,
        title="Done: CANCEL SUBSCRIPTION",
        summary=content,
        household_id=household_id,
        user_id=request_user_id,
        draft_id=draft.id,
        execution_id=execution.id,
        vendor=draft.vendor,
        estimated_cost_cents=None,
        body={"confirmation_id": confirmation_id, "subscription": sub},
        actions=[],
        warnings=[],
    )


def _execute_book_appointment(db: Session, draft: Draft, execution: Execution) -> CardV1:
    household_id, request_user_id = _draft_context(db, draft)

    payload = draft.draft_payload_json or {}

    try:
        adapter = get_booking_adapter()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if draft.vendor != adapter.vendor:
        raise HTTPException(status_code=409, detail="Draft vendor mismatch")

    try:
        result = adapter.execute(household_id, draft_payload=payload)
    except Exception as e:
        _raise_booking_http_error(e)

    idx = int(payload.get("selected_time_window_index") or 0)
    windows = payload.get("time_windows") or []
    selected = windows[idx] if isinstance(windows, list) and len(windows) > idx else {}

    execution.status = "DONE"
    execution.finished_at = datetime.utcnow()
    execution.final_cost_cents = int(payload.get("price_estimate_cents") or 0)
    execution.execution_payload_json = {
        "confirmation_id": result.confirmation_id,
        "details": {
            "service_type": payload.get("service_type"),
            "vendor_name": payload.get("vendor_name"),
            "time_window": selected,
        },
    }

    receipt_row_id = uuid4().hex
    db.add(
        ReceiptArtifact(
            id=receipt_row_id,
            execution_id=execution.id,
            type="BOOKING_CONFIRMATION",
            content_text=result.summary,
            external_reference_id=result.external_reference_id or result.confirmation_id,
        )
    )

    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="Execution",
        entity_id=execution.id,
        event_type="EXECUTION_DONE",
        event_payload=execution.execution_payload_json,
    )
    _log_event(
        db,
        household_id=household_id,
        user_id=request_user_id,
        entity_type="ReceiptArtifact",
        entity_id=receipt_row_id,
        event_type="RECEIPT_CREATED",
        event_payload={
            "type": "BOOKING_CONFIRMATION",
            "external_reference_id": result.external_reference_id or result.confirmation_id,
        },
    )

    db.commit()

    return CardV1(
        type=CardTypeV1.DONE,
        title="Done: BOOK APPOINTMENT",
        summary=result.summary,
        household_id=household_id,
        user_id=request_user_id,
        draft_id=draft.id,
        execution_id=execution.id,
        vendor=draft.vendor,
        estimated_cost_cents=int(payload.get("price_estimate_cents") or 0),
        body={
            "confirmation_id": result.confirmation_id,
            "details": execution.execution_payload_json,
        },
        actions=[],
        warnings=[],
    )


def _draft_to_card(db: Session, draft: Draft, household_id: str, request_user_id: str) -> CardV1:
    payload = draft.draft_payload_json or {}

    if draft.verb == "REORDER":
        items = payload.get("items") or []
        return CardV1(
            type=CardTypeV1.DRAFT,
            title="Draft: REORDER",
            summary=f"I will reorder {len(items)} item(s) from Amazon.",
            household_id=household_id,
            user_id=request_user_id,
            draft_id=draft.id,
            vendor=draft.vendor,
            estimated_cost_cents=draft.estimated_cost_cents,
            body={
                "items": items,
                "delivery_window": payload.get("delivery_window"),
                "payment_method_masked": payload.get("payment_method_masked"),
            },
            actions=[
                CardActionV1(type=CardActionTypeV1.CONFIRM, label="Confirm", payload={}),
                CardActionV1(type=CardActionTypeV1.MODIFY, label="Modify", payload={}),
                CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={}),
            ],
            warnings=payload.get("warnings") or [],
        )

    if draft.verb == "CANCEL_SUBSCRIPTION":
        sub = payload.get("subscription") or {}
        return CardV1(
            type=CardTypeV1.DRAFT,
            title="Draft: CANCEL SUBSCRIPTION",
            summary=f"I will cancel {sub.get('name')}.",
            household_id=household_id,
            user_id=request_user_id,
            draft_id=draft.id,
            vendor=draft.vendor,
            estimated_cost_cents=None,
            body=sub,
            actions=[
                CardActionV1(type=CardActionTypeV1.CONFIRM, label="Confirm", payload={}),
                CardActionV1(type=CardActionTypeV1.MODIFY, label="Modify", payload={}),
                CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={}),
            ],
            warnings=payload.get("warnings") or [],
        )

    if draft.verb == "BOOK_APPOINTMENT":
        return CardV1(
            type=CardTypeV1.DRAFT,
            title="Draft: BOOK APPOINTMENT",
            summary=(
                f"I will book {payload.get('service_type')} with {payload.get('vendor_name')}"
            ),
            household_id=household_id,
            user_id=request_user_id,
            draft_id=draft.id,
            vendor=draft.vendor,
            estimated_cost_cents=draft.estimated_cost_cents,
            body={
                "service_type": payload.get("service_type"),
                "vendor_name": payload.get("vendor_name"),
                "price_estimate_cents": payload.get("price_estimate_cents"),
                "time_windows": payload.get("time_windows") or [],
                "selected_time_window_index": payload.get("selected_time_window_index") or 0,
            },
            actions=[
                CardActionV1(type=CardActionTypeV1.CONFIRM, label="Confirm", payload={}),
                CardActionV1(type=CardActionTypeV1.MODIFY, label="Modify", payload={}),
                CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={}),
            ],
            warnings=[],
        )

    raise HTTPException(status_code=409, detail=f"Unknown draft verb: {draft.verb}")


def _draft_context(db: Session, draft: Draft) -> tuple[str, str]:
    req = db.get(ExecutionRequest, draft.execution_request_id)
    if req is None:
        return ("", "")
    return (req.household_id, req.user_id)


def _log_event(
    db: Session,
    *,
    household_id: str,
    user_id: str | None,
    entity_type: str,
    entity_id: str,
    event_type: str,
    event_payload: dict,
) -> None:
    db.add(
        EventLog(
            id=uuid4().hex,
            household_id=household_id,
            user_id=user_id,
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            event_payload_json=event_payload,
        )
    )


def _raise_booking_http_error(e: Exception) -> None:
    if isinstance(e, BookingLinkRequiredError):
        raise HTTPException(status_code=412, detail=str(e)) from e

    if isinstance(e, BookingPlaywrightMissingError):
        raise HTTPException(status_code=503, detail=str(e)) from e

    if isinstance(e, NotImplementedError):
        raise HTTPException(status_code=501, detail=str(e)) from e

    if isinstance(e, BookingAdapterError):
        raise HTTPException(status_code=502, detail=str(e)) from e

    raise HTTPException(status_code=500, detail="Internal Server Error") from e


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
