"""Shared message card payload schema (v1).

The iMessage extension and the iOS audit app should render these payloads consistently.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CardTypeV1(str, Enum):
    DRAFT = "DRAFT"
    STATUS = "STATUS"
    DONE = "DONE"
    FAILED = "FAILED"
    CLARIFY = "CLARIFY"
    UNSUPPORTED = "UNSUPPORTED"


class CardActionTypeV1(str, Enum):
    CONFIRM = "CONFIRM"
    MODIFY = "MODIFY"
    CANCEL = "CANCEL"
    RETRY = "RETRY"


class CardActionV1(BaseModel):
    type: CardActionTypeV1
    label: str
    payload: dict[str, Any] = Field(default_factory=dict)


class CardV1(BaseModel):
    version: str = "1"
    type: CardTypeV1

    title: str
    summary: str

    # Server-side IDs to support follow-up actions.
    household_id: str
    user_id: str
    draft_id: str | None = None
    execution_id: str | None = None

    vendor: str | None = None
    estimated_cost_cents: int | None = None

    # Verb-specific rendering payload.
    body: dict[str, Any] = Field(default_factory=dict)

    actions: list[CardActionV1] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list, max_length=8)
