from __future__ import annotations

from pydantic import BaseModel, Field


class ReceiptArtifactOut(BaseModel):
    id: str
    type: str
    content_text: str
    external_reference_id: str | None = None
    created_at: str


class ExecutionListItem(BaseModel):
    execution_id: str
    draft_id: str
    verb: str
    status: str
    started_at: str
    finished_at: str | None = None

    vendor: str
    final_cost_cents: int | None = None


class ExecutionDetail(BaseModel):
    execution_id: str
    draft_id: str
    verb: str
    status: str

    started_at: str
    finished_at: str | None = None

    raw_command_text: str
    normalized_intent_json: dict = Field(default_factory=dict)

    draft_payload_json: dict = Field(default_factory=dict)
    confirmation_latency_ms: int | None = None

    execution_payload_json: dict = Field(default_factory=dict)
    error_message: str | None = None

    receipts: list[ReceiptArtifactOut] = Field(default_factory=list)
