"""Shared event schema (v1).

The backend stores an append-only event log. Clients can consume these events to render
an audit trail.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EntityTypeV1(str, Enum):
    EXECUTION_REQUEST = "ExecutionRequest"
    DRAFT = "Draft"
    CONFIRMATION = "Confirmation"
    EXECUTION = "Execution"
    RECEIPT_ARTIFACT = "ReceiptArtifact"


class EventTypeV1(str, Enum):
    COMMAND_RECEIVED = "COMMAND_RECEIVED"
    INTENT_EXTRACTED = "INTENT_EXTRACTED"
    DRAFT_CREATED = "DRAFT_CREATED"
    DRAFT_MODIFIED = "DRAFT_MODIFIED"
    DRAFT_CONFIRMED = "DRAFT_CONFIRMED"
    EXECUTION_STARTED = "EXECUTION_STARTED"
    EXECUTION_ATTEMPTED = "EXECUTION_ATTEMPTED"
    EXECUTION_DONE = "EXECUTION_DONE"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RECEIPT_CREATED = "RECEIPT_CREATED"


class EventV1(BaseModel):
    id: str
    household_id: str
    user_id: str | None = None

    entity_type: EntityTypeV1
    entity_id: str

    event_type: EventTypeV1
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
