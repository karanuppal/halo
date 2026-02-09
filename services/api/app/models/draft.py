from __future__ import annotations

from pydantic import BaseModel, Field


class DraftModifyRequest(BaseModel):
    draft_id: str
    modifications: dict = Field(default_factory=dict)


class DraftConfirmRequest(BaseModel):
    draft_id: str
    user_id: str
