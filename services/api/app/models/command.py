from __future__ import annotations

from pydantic import BaseModel, Field


class CommandParseRequest(BaseModel):
    household_id: str
    user_id: str
    channel: str = "API"
    raw_command_text: str = Field(..., min_length=1)

    # Map of clarification question id -> answer.
    clarification_answers: dict[str, str] = Field(default_factory=dict)
