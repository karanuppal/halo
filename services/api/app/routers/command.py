from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from packages.shared.schemas.card_v1 import (
    CardActionTypeV1,
    CardActionV1,
    CardTypeV1,
    CardV1,
)
from packages.shared.schemas.intent import ClarificationQuestionV1, IntentV1, VerbV1
from services.api.app.db.deps import get_db
from services.api.app.db.models import (
    BookingVendor,
    Draft,
    EventLog,
    ExecutionRequest,
    Household,
    Preference,
    Subscription,
    User,
    UsualItem,
)
from services.api.app.llm.factory import get_intent_extractor
from services.api.app.models.command import CommandParseRequest
from services.api.app.models.order import OrderItemInput
from services.api.app.services.amazon_base import (
    AmazonAdapterError,
    AmazonBotCheckError,
    AmazonCheckoutTotalDriftError,
    AmazonLinkRequiredError,
    AmazonPlaywrightMissingError,
)
from services.api.app.services.amazon_factory import get_amazon_adapter
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/v1/command/parse", response_model=IntentV1)
def parse_command(payload: CommandParseRequest) -> IntentV1:
    try:
        extractor = get_intent_extractor()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return extractor.extract(
        raw_command_text=payload.raw_command_text,
        household_id=payload.household_id,
        user_id=payload.user_id,
        clarification_answers=payload.clarification_answers,
    )


@router.post("/v1/command", response_model=CardV1)
def submit_command(payload: CommandParseRequest, db: Session = Depends(get_db)) -> CardV1:
    _ensure_household_user(db, payload.household_id, payload.user_id)

    try:
        extractor = get_intent_extractor()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    intent = extractor.extract(
        raw_command_text=payload.raw_command_text,
        household_id=payload.household_id,
        user_id=payload.user_id,
        clarification_answers=payload.clarification_answers,
    )

    execution_request_id = uuid4().hex
    db.add(
        ExecutionRequest(
            id=execution_request_id,
            household_id=payload.household_id,
            user_id=payload.user_id,
            channel=payload.channel,
            raw_command_text=payload.raw_command_text,
            normalized_intent_json=intent.model_dump(mode="json"),
        )
    )

    _log_event(
        db,
        household_id=payload.household_id,
        user_id=payload.user_id,
        entity_type="ExecutionRequest",
        entity_id=execution_request_id,
        event_type="COMMAND_RECEIVED",
        event_payload={"channel": payload.channel, "raw_command_text": payload.raw_command_text},
    )
    _log_event(
        db,
        household_id=payload.household_id,
        user_id=payload.user_id,
        entity_type="ExecutionRequest",
        entity_id=execution_request_id,
        event_type="INTENT_EXTRACTED",
        event_payload=intent.model_dump(mode="json"),
    )
    db.commit()

    if intent.clarifications:
        return CardV1(
            type=CardTypeV1.CLARIFY,
            title="Clarify",
            summary="I need 1-2 quick answers before I can draft this.",
            household_id=payload.household_id,
            user_id=payload.user_id,
            vendor=None,
            estimated_cost_cents=None,
            body={
                "intent": intent.model_dump(mode="json"),
                "questions": [q.model_dump(mode="json") for q in intent.clarifications],
            },
            actions=[
                CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={}),
            ],
            warnings=[],
        )

    if intent.verb == VerbV1.UNSUPPORTED or intent.confidence < 0.55:
        return CardV1(
            type=CardTypeV1.UNSUPPORTED,
            title="Not supported yet",
            summary="Halo can’t do that digitally yet in MVP.",
            household_id=payload.household_id,
            user_id=payload.user_id,
            vendor=None,
            estimated_cost_cents=None,
            body={
                "supported": [
                    "REORDER",
                    "CANCEL_SUBSCRIPTION",
                    "BOOK_APPOINTMENT",
                ],
                "intent": intent.model_dump(mode="json"),
            },
            actions=[],
            warnings=[],
        )

    if intent.verb == VerbV1.REORDER:
        return _draft_reorder(db, payload, execution_request_id, intent)

    if intent.verb == VerbV1.CANCEL_SUBSCRIPTION:
        return _draft_cancel_subscription(db, payload, execution_request_id, intent)

    if intent.verb == VerbV1.BOOK_APPOINTMENT:
        return _draft_book_appointment(db, payload, execution_request_id, intent)

    # Should be unreachable due to schema validation, but fail closed.
    return CardV1(
        type=CardTypeV1.UNSUPPORTED,
        title="Not supported yet",
        summary="Halo can’t do that digitally yet in MVP.",
        household_id=payload.household_id,
        user_id=payload.user_id,
        body={"intent": intent.model_dump(mode="json")},
        actions=[],
        warnings=[],
    )


def _draft_reorder(
    db: Session,
    payload: CommandParseRequest,
    execution_request_id: str,
    intent: IntentV1,
) -> CardV1:
    try:
        adapter = get_amazon_adapter()
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    items = _reorder_items_from_intent_or_usual(db, payload.household_id, intent)

    try:
        draft = adapter.build_draft(payload.household_id, items)
    except Exception as e:
        _raise_adapter_http_error(e)

    draft_id = uuid4().hex

    draft_payload = {
        "verb": "REORDER",
        "vendor": adapter.vendor,
        "intent": intent.model_dump(mode="json"),
        "items": [i.model_dump(mode="json") for i in draft.items],
        "estimated_total_cents": draft.estimated_total_cents,
        "delivery_window": draft.delivery_window,
        "payment_method_masked": draft.payment_method_masked,
        "warnings": draft.warnings,
    }

    db.add(
        Draft(
            id=draft_id,
            execution_request_id=execution_request_id,
            verb="REORDER",
            vendor=adapter.vendor,
            estimated_cost_cents=draft.estimated_total_cents,
            draft_payload_json=draft_payload,
        )
    )

    _log_event(
        db,
        household_id=payload.household_id,
        user_id=payload.user_id,
        entity_type="Draft",
        entity_id=draft_id,
        event_type="DRAFT_CREATED",
        event_payload=draft_payload,
    )

    db.commit()

    return CardV1(
        type=CardTypeV1.DRAFT,
        title="Draft: REORDER",
        summary=f"I will reorder {len(draft.items)} item(s) from Amazon.",
        household_id=payload.household_id,
        user_id=payload.user_id,
        draft_id=draft_id,
        vendor=adapter.vendor,
        estimated_cost_cents=draft.estimated_total_cents,
        body={
            "items": [i.model_dump(mode="json") for i in draft.items],
            "delivery_window": draft.delivery_window,
            "payment_method_masked": draft.payment_method_masked,
        },
        actions=[
            CardActionV1(type=CardActionTypeV1.CONFIRM, label="Confirm", payload={}),
            CardActionV1(type=CardActionTypeV1.MODIFY, label="Modify", payload={}),
            CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={}),
        ],
        warnings=draft.warnings,
    )


def _draft_cancel_subscription(
    db: Session,
    payload: CommandParseRequest,
    execution_request_id: str,
    intent: IntentV1,
) -> CardV1:
    _ensure_default_subscriptions(db, payload.household_id)

    sub_name = (
        str(intent.params.get("subscription_name") or "").strip() or (intent.object or "").strip()
    )

    subs = (
        db.query(Subscription)
        .filter(Subscription.household_id == payload.household_id)
        .order_by(Subscription.name.asc())
        .all()
    )

    match = None
    for s in subs:
        if s.name.lower() == sub_name.lower() and sub_name:
            match = s
            break

    if match is None:
        questions = [
            ClarificationQuestionV1(
                id="q0",
                prompt="Which subscription should I cancel?",
                choices=[s.name for s in subs][:8],
            )
        ]
        return CardV1(
            type=CardTypeV1.CLARIFY,
            title="Clarify: cancel subscription",
            summary="I need you to pick a subscription.",
            household_id=payload.household_id,
            user_id=payload.user_id,
            body={
                "intent": intent.model_dump(mode="json"),
                "questions": [q.model_dump(mode="json") for q in questions],
            },
            actions=[CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={})],
            warnings=[],
        )

    draft_id = uuid4().hex
    warnings = [
        "This may be irreversible and could take effect immediately.",
    ]

    draft_payload = {
        "verb": "CANCEL_SUBSCRIPTION",
        "vendor": "MOCK_SUBS",
        "intent": intent.model_dump(mode="json"),
        "subscription": {
            "id": match.id,
            "name": match.name,
            "monthly_cost_cents": match.monthly_cost_cents,
            "renewal_date": match.renewal_date.isoformat(),
        },
        "warnings": warnings,
    }

    db.add(
        Draft(
            id=draft_id,
            execution_request_id=execution_request_id,
            verb="CANCEL_SUBSCRIPTION",
            vendor="MOCK_SUBS",
            estimated_cost_cents=None,
            draft_payload_json=draft_payload,
        )
    )

    _log_event(
        db,
        household_id=payload.household_id,
        user_id=payload.user_id,
        entity_type="Draft",
        entity_id=draft_id,
        event_type="DRAFT_CREATED",
        event_payload=draft_payload,
    )

    db.commit()

    return CardV1(
        type=CardTypeV1.DRAFT,
        title="Draft: CANCEL SUBSCRIPTION",
        summary=f"I will cancel {match.name}.",
        household_id=payload.household_id,
        user_id=payload.user_id,
        draft_id=draft_id,
        vendor="MOCK_SUBS",
        estimated_cost_cents=None,
        body=draft_payload["subscription"],
        actions=[
            CardActionV1(type=CardActionTypeV1.CONFIRM, label="Confirm", payload={}),
            CardActionV1(type=CardActionTypeV1.MODIFY, label="Modify", payload={}),
            CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={}),
        ],
        warnings=warnings,
    )


def _draft_book_appointment(
    db: Session,
    payload: CommandParseRequest,
    execution_request_id: str,
    intent: IntentV1,
) -> CardV1:
    vendor = _ensure_default_booking_vendor(db, payload.household_id)

    service_type = str(
        intent.params.get("service_type") or intent.object or vendor.default_service_type
    )
    service_type = service_type.strip() or vendor.default_service_type

    windows = _default_time_windows()
    selected = 0

    draft_id = uuid4().hex
    draft_payload = {
        "verb": "BOOK_APPOINTMENT",
        "vendor": "MOCK_BOOKING",
        "intent": intent.model_dump(mode="json"),
        "service_type": service_type,
        "vendor_name": vendor.name,
        "price_estimate_cents": vendor.price_estimate_cents,
        "time_windows": windows,
        "selected_time_window_index": selected,
    }

    db.add(
        Draft(
            id=draft_id,
            execution_request_id=execution_request_id,
            verb="BOOK_APPOINTMENT",
            vendor="MOCK_BOOKING",
            estimated_cost_cents=vendor.price_estimate_cents,
            draft_payload_json=draft_payload,
        )
    )

    _log_event(
        db,
        household_id=payload.household_id,
        user_id=payload.user_id,
        entity_type="Draft",
        entity_id=draft_id,
        event_type="DRAFT_CREATED",
        event_payload=draft_payload,
    )

    db.commit()

    return CardV1(
        type=CardTypeV1.DRAFT,
        title="Draft: BOOK APPOINTMENT",
        summary=f"I will book {service_type} with {vendor.name}.",
        household_id=payload.household_id,
        user_id=payload.user_id,
        draft_id=draft_id,
        vendor="MOCK_BOOKING",
        estimated_cost_cents=vendor.price_estimate_cents,
        body={
            "service_type": service_type,
            "vendor_name": vendor.name,
            "price_estimate_cents": vendor.price_estimate_cents,
            "time_windows": windows,
            "selected_time_window_index": selected,
        },
        actions=[
            CardActionV1(type=CardActionTypeV1.CONFIRM, label="Confirm", payload={}),
            CardActionV1(type=CardActionTypeV1.MODIFY, label="Modify", payload={}),
            CardActionV1(type=CardActionTypeV1.CANCEL, label="Cancel", payload={}),
        ],
        warnings=[],
    )


def _ensure_household_user(db: Session, household_id: str, user_id: str) -> None:
    household = db.get(Household, household_id)
    if household is None:
        db.add(Household(id=household_id, name=household_id))

    user = db.get(User, user_id)
    if user is None:
        db.add(User(id=user_id, household_id=household_id, display_name=user_id))

    pref = db.get(Preference, household_id)
    if pref is None:
        db.add(
            Preference(
                household_id=household_id,
                default_merchant="amazon",
                default_booking_vendor=None,
            )
        )

    db.commit()


def _ensure_default_usual_items(db: Session, household_id: str) -> None:
    if db.query(UsualItem).filter(UsualItem.household_id == household_id).limit(1).count() > 0:
        return

    defaults = [
        ("paper towels", 1),
        ("detergent", 1),
    ]
    for name, qty in defaults:
        db.add(UsualItem(id=uuid4().hex, household_id=household_id, name=name, quantity=qty))

    db.commit()


def _ensure_default_subscriptions(db: Session, household_id: str) -> None:
    existing = (
        db.query(Subscription).filter(Subscription.household_id == household_id).limit(1).count()
    )
    if existing > 0:
        return

    now = datetime.utcnow()
    defaults = [
        ("Netflix", 1599, now + timedelta(days=15)),
        ("Spotify", 1099, now + timedelta(days=7)),
    ]

    for name, cost, renewal in defaults:
        db.add(
            Subscription(
                id=uuid4().hex,
                household_id=household_id,
                name=name,
                monthly_cost_cents=cost,
                renewal_date=renewal,
            )
        )

    db.commit()


def _ensure_default_booking_vendor(db: Session, household_id: str) -> BookingVendor:
    vendor = (
        db.query(BookingVendor)
        .filter(BookingVendor.household_id == household_id)
        .order_by(BookingVendor.created_at.asc())
        .first()
    )
    if vendor is not None:
        return vendor

    vendor = BookingVendor(
        id=uuid4().hex,
        household_id=household_id,
        name="Mock Cleaner Co",
        default_service_type="cleaning",
        price_estimate_cents=12000,
    )
    db.add(vendor)
    db.commit()
    return vendor


def _reorder_items_from_intent_or_usual(
    db: Session,
    household_id: str,
    intent: IntentV1,
) -> list[OrderItemInput]:
    raw_items = intent.params.get("items") if isinstance(intent.params, dict) else None

    if isinstance(raw_items, list) and raw_items:
        out: list[OrderItemInput] = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or "").strip()
            qty = int(it.get("quantity") or 1)
            if not name:
                continue
            out.append(OrderItemInput(name=name, quantity=max(1, qty)))
        if out:
            return out

    _ensure_default_usual_items(db, household_id)
    usual = (
        db.query(UsualItem)
        .filter(UsualItem.household_id == household_id)
        .order_by(UsualItem.created_at.asc())
        .all()
    )

    return [OrderItemInput(name=u.name, quantity=u.quantity) for u in usual]


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


def _default_time_windows() -> list[dict[str, str]]:
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    base = now + timedelta(days=1)
    return [
        {
            "start": (base.replace(hour=9)).isoformat() + "Z",
            "end": (base.replace(hour=11)).isoformat() + "Z",
        },
        {
            "start": (base.replace(hour=12)).isoformat() + "Z",
            "end": (base.replace(hour=14)).isoformat() + "Z",
        },
        {
            "start": (base.replace(hour=15)).isoformat() + "Z",
            "end": (base.replace(hour=17)).isoformat() + "Z",
        },
    ]


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
