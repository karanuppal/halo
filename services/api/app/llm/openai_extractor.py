from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from packages.shared.schemas.intent import ClarificationQuestionV1, IntentV1, VerbV1


class OpenAIIntentExtractor:
    """Intent extraction via OpenAI.

    This uses a strict JSON-only response and validates against IntentV1.
    """

    def __init__(self, *, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    def extract(
        self,
        *,
        raw_command_text: str,
        household_id: str,
        user_id: str,
        clarification_answers: dict[str, str] | None = None,
    ) -> IntentV1:
        del household_id, user_id
        clarification_answers = clarification_answers or {}

        system = _SYSTEM_PROMPT
        user_payload = {
            "command": raw_command_text,
            "clarification_answers": clarification_answers,
        }

        try:
            content = _openai_chat_json(
                api_key=self._api_key,
                model=self._model,
                system_prompt=system,
                user_json=user_payload,
            )
            data = json.loads(content)
            return IntentV1.model_validate(data)
        except Exception as e:
            # Fail closed: do not guess execution details.
            return IntentV1(
                verb=VerbV1.UNSUPPORTED,
                object="",
                params={"error": str(e)},
                confidence=0.0,
                routine_key="UNSUPPORTED",
                clarifications=[
                    ClarificationQuestionV1(
                        id="q0",
                        prompt=(
                            "Which action do you want Halo to take?"
                            " (Supported: REORDER, CANCEL_SUBSCRIPTION, BOOK_APPOINTMENT)"
                        ),
                        choices=["REORDER", "CANCEL_SUBSCRIPTION", "BOOK_APPOINTMENT"],
                    )
                ],
            )


def _openai_chat_json(
    *,
    api_key: str,
    model: str,
    system_prompt: str,
    user_json: dict,
) -> str:
    url = "https://api.openai.com/v1/chat/completions"

    body = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_json)},
        ],
        # Ask for JSON object only.
        "response_format": {"type": "json_object"},
    }

    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, data=json.dumps(body).encode("utf-8"), timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI HTTP {e.code}: {raw}") from e

    try:
        return payload["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Unexpected OpenAI response shape: {payload!r}") from e


_SYSTEM_PROMPT = """You are an intent extraction engine for Halo.

Halo is a household autopilot-in-training.

You MUST return a single JSON object that conforms to this schema:

{
  "verb": "REORDER" | "CANCEL_SUBSCRIPTION" | "BOOK_APPOINTMENT" | "UNSUPPORTED",
  "object": string,
  "params": object,
  "confidence": number (0..1),
  "routine_key": string,
  "clarifications": [
    { "id": string, "prompt": string, "choices": [string] }
  ]
}

Rules:
- Halo MVP supports exactly 3 verbs: REORDER, CANCEL_SUBSCRIPTION, BOOK_APPOINTMENT.
- If the request is outside scope, set verb=UNSUPPORTED and confidence <= 0.5.
- If required info is missing or ambiguous, include 1-2 clarification questions (max 2)
  in "clarifications".
- Clarifications must be concise, goal-oriented, and not chatty.
- If clarifications is non-empty, do NOT invent missing params.
- routine_key should be stable, e.g. "REORDER:USUAL", "CANCEL_SUBSCRIPTION:netflix",
  "BOOK_APPOINTMENT:cleaning".

REORDER params:
- Prefer {"usual": true} when user implies "usual" or recurring restock.
- If user specifies items, use {"items": [{"name": string, "quantity": int}]}.

CANCEL_SUBSCRIPTION params:
- Use {"subscription_name": string}.

BOOK_APPOINTMENT params:
- Use {"service_type": string, "time_preference": string}.

Input: you will receive a JSON object with fields:
- command: the user's natural language instruction
- clarification_answers: a JSON object mapping question ids to answers (may be empty)
"""


def default_openai_model() -> str:
    return os.getenv("HALO_LLM_MODEL", "gpt-4o-mini")
