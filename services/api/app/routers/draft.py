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
        _emit_autopilot_signal(
            db,
            draft=draft,
            execution=execution,
            household_id=household_id,
            user_id=payload.user_id or request_user_id,
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


@router.get("/v1/drafts/{draft_id}", response_model=CardV1)
def get_draft(draft_id: str, db: Session = Depends(get_db)) -> CardV1:
    draft = db.get(Draft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    household_id, request_user_id = _draft_context(db, draft)
    return _draft_to_card(db, draft, household_id, request_user_id)


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
    _emit_autopilot_signal(
        db,
        draft=draft,
        execution=execution,
        household_id=household_id,
        user_id=request_user_id,
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
    _emit_autopilot_signal(
        db,
        draft=draft,
        execution=execution,
        household_id=household_id,
        user_id=request_user_id,
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
    _emit_autopilot_signal(
        db,
        draft=draft,
        execution=execution,
        household_id=household_id,
        user_id=request_user_id,
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
            body={
                **sub,
                "available_subscriptions": payload.get("available_subscriptions") or [],
            },
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


def _emit_autopilot_signal(
    db: Session,
    *,
    draft: Draft,
    execution: Execution,
    household_id: str,
    user_id: str | None,
) -> None:
    """Best-effort autopilot-readiness telemetry.

    This must never block user-visible execution flow.
    """

    try:
        db.flush()

        routine_key = _routine_key_from_draft(draft)

        rows = (
            db.query(Execution, Draft, ExecutionRequest)
            .join(Draft, Draft.id == Execution.draft_id)
            .join(ExecutionRequest, ExecutionRequest.id == Draft.execution_request_id)
            .filter(ExecutionRequest.household_id == household_id)
            .order_by(Execution.started_at.asc())
            .all()
        )

        routine_done: list[tuple[Execution, Draft]] = []
        adapter_total = 0
        adapter_failed = 0

        for hist_execution, hist_draft, hist_req in rows:
            if hist_draft.vendor == draft.vendor:
                adapter_total += 1
                if hist_execution.status == "FAILED":
                    adapter_failed += 1

            hist_key = str((hist_req.normalized_intent_json or {}).get("routine_key") or "")
            if hist_key != routine_key or hist_execution.id == execution.id:
                continue

            if hist_execution.status == "DONE" and hist_execution.finished_at is not None:
                routine_done.append((hist_execution, hist_draft))

        repeats_count = len(routine_done) + (1 if execution.status == "DONE" else 0)

        completed_times = [hist_execution.finished_at for hist_execution, _ in routine_done]
        completed_times = [t for t in completed_times if t is not None]
        completed_times.sort()

        reference_time = (
            execution.finished_at if execution.status == "DONE" else execution.started_at
        )
        time_since_last_completion_ms: int | None = None
        if completed_times and reference_time is not None:
            time_since_last_completion_ms = int(
                (reference_time - completed_times[-1]).total_seconds() * 1000
            )

        series = list(completed_times)
        if execution.status == "DONE" and execution.finished_at is not None:
            series.append(execution.finished_at)

        average_interval_ms: int | None = None
        if len(series) >= 2:
            intervals = [
                int((series[i] - series[i - 1]).total_seconds() * 1000)
                for i in range(1, len(series))
            ]
            average_interval_ms = int(sum(intervals) / len(intervals))

        current_items = _item_quantities_from_payload(draft.draft_payload_json or {})
        prev_items = (
            _item_quantities_from_payload(routine_done[-1][1].draft_payload_json or {})
            if routine_done
            else {}
        )
        item_changes_count = (
            _item_change_count(current_items, prev_items) if current_items else None
        )

        previous_costs = [
            hist_execution.final_cost_cents
            for hist_execution, _ in routine_done
            if hist_execution.final_cost_cents is not None
        ]
        baseline_cost_cents = (
            int(sum(previous_costs) / len(previous_costs)) if previous_costs else None
        )
        cost_deviation_cents: int | None = None
        if execution.final_cost_cents is not None and baseline_cost_cents is not None:
            cost_deviation_cents = execution.final_cost_cents - baseline_cost_cents

        confirmation = (
            db.query(Confirmation)
            .filter(Confirmation.draft_id == draft.id)
            .order_by(Confirmation.confirmed_at.desc())
            .first()
        )
        confirmation_latency_ms = confirmation.confirmation_latency_ms if confirmation else None

        modify_count = (
            db.query(EventLog)
            .filter(
                EventLog.entity_type == "Draft",
                EventLog.entity_id == draft.id,
                EventLog.event_type == "DRAFT_MODIFIED",
            )
            .count()
        )

        failure_rate = round(adapter_failed / adapter_total, 4) if adapter_total else 0.0

        signal_payload = {
            "routine_key": routine_key,
            "status": execution.status,
            "repeats_count": repeats_count,
            "cadence": {
                "time_since_last_completion_ms": time_since_last_completion_ms,
                "average_interval_ms": average_interval_ms,
            },
            "variance": {
                "item_changes_count": item_changes_count,
                "baseline_cost_cents": baseline_cost_cents,
                "cost_deviation_cents": cost_deviation_cents,
            },
            "trust": {
                "confirmation_latency_ms": confirmation_latency_ms,
                "modify_count_before_confirm": modify_count,
            },
            "adapter": {
                "vendor": draft.vendor,
                "failed_executions": adapter_failed,
                "total_executions": adapter_total,
                "failure_rate": failure_rate,
            },
        }

        _log_event(
            db,
            household_id=household_id,
            user_id=user_id,
            entity_type="Execution",
            entity_id=execution.id,
            event_type="AUTOPILOT_SIGNAL_COMPUTED",
            event_payload=signal_payload,
        )
    except Exception:
        # Telemetry is best-effort; user-facing flow should never fail because of it.
        return


def _routine_key_from_draft(draft: Draft) -> str:
    payload = draft.draft_payload_json or {}
    intent = payload.get("intent") if isinstance(payload, dict) else {}
    if isinstance(intent, dict):
        rk = str(intent.get("routine_key") or "").strip()
        if rk:
            return rk
    return f"{draft.verb}:UNKNOWN"


def _item_quantities_from_payload(payload: dict) -> dict[str, int]:
    out: dict[str, int] = {}
    raw_items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return out

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip().lower()
        if not name:
            continue
        try:
            qty = max(1, int(raw.get("quantity") or 1))
        except Exception:
            qty = 1
        out[name] = qty

    return out


def _item_change_count(current: dict[str, int], previous: dict[str, int]) -> int:
    keys = set(current) | set(previous)
    return sum(abs(current.get(k, 0) - previous.get(k, 0)) for k in keys)


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
