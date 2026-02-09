from __future__ import annotations

from typing import Protocol

from packages.shared.schemas.intent import IntentV1


class IntentExtractor(Protocol):
    def extract(
        self,
        *,
        raw_command_text: str,
        household_id: str,
        user_id: str,
        clarification_answers: dict[str, str] | None = None,
    ) -> IntentV1: ...
