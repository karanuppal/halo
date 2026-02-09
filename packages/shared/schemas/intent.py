"""Shared intent schema (v1).

These models are intended to be shared between backend and clients (iOS).
They should remain stable and backwards compatible once shipped.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VerbV1(str, Enum):
    REORDER = "REORDER"
    CANCEL_SUBSCRIPTION = "CANCEL_SUBSCRIPTION"
    BOOK_APPOINTMENT = "BOOK_APPOINTMENT"
    UNSUPPORTED = "UNSUPPORTED"


class ClarificationQuestionV1(BaseModel):
    """A bounded clarification prompt.

    This is not chat. It is a short question with optional choices.
    """

    prompt: str
    choices: list[str] = Field(default_factory=list, max_length=8)


class IntentV1(BaseModel):
    verb: VerbV1
    object: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(..., ge=0.0, le=1.0)
    routine_key: str

    # If present, the client should ask these questions and then resubmit with answers.
    clarifications: list[ClarificationQuestionV1] = Field(default_factory=list, max_length=2)
