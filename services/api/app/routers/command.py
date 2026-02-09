from __future__ import annotations

from fastapi import APIRouter, HTTPException
from packages.shared.schemas.intent import IntentV1
from services.api.app.llm.factory import get_intent_extractor
from services.api.app.models.command import CommandParseRequest

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
