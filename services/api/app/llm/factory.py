from __future__ import annotations

import os

from services.api.app.llm.base import IntentExtractor
from services.api.app.llm.fake import FakeIntentExtractor


def get_intent_extractor() -> IntentExtractor:
    """Select the intent extractor.

    Default is deterministic fake to keep local dev and tests stable.
    Set HALO_LLM_PROVIDER=openai and OPENAI_API_KEY to enable OpenAI.
    """

    provider = os.getenv("HALO_LLM_PROVIDER", "fake").strip().lower()

    if provider == "fake":
        return FakeIntentExtractor()

    if provider == "openai":
        from services.api.app.llm.openai_extractor import (
            OpenAIIntentExtractor,
            default_openai_model,
        )

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required when HALO_LLM_PROVIDER=openai")

        return OpenAIIntentExtractor(api_key=api_key, model=default_openai_model())

    raise ValueError(f"Unknown HALO_LLM_PROVIDER={provider!r}. Expected fake or openai.")
