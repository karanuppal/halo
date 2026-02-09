from __future__ import annotations

import re

from packages.shared.schemas.intent import ClarificationQuestionV1, IntentV1, VerbV1


class FakeIntentExtractor:
    """Deterministic intent extractor for tests and local dev.

    This is not intended to be "smart". In production, use the OpenAI extractor.
    """

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

        text = (raw_command_text or "").strip().lower()

        # Cancel subscription
        if any(k in text for k in ("cancel", "unsubscribe", "stop")):
            sub = _extract_subscription_name(text) or clarification_answers.get("q0", "").strip()
            if not sub:
                return IntentV1(
                    verb=VerbV1.CANCEL_SUBSCRIPTION,
                    object="",
                    params={},
                    confidence=0.35,
                    routine_key="CANCEL_SUBSCRIPTION",
                    clarifications=[
                        ClarificationQuestionV1(
                            id="q0",
                            prompt="Which subscription should I cancel?",
                            choices=["Netflix", "Spotify"],
                        )
                    ],
                )

            return IntentV1(
                verb=VerbV1.CANCEL_SUBSCRIPTION,
                object=sub,
                params={"subscription_name": sub},
                confidence=0.85,
                routine_key=f"CANCEL_SUBSCRIPTION:{sub.lower()}",
                clarifications=[],
            )

        # Book appointment
        if any(k in text for k in ("book", "schedule", "reservation", "reserve")):
            service = _extract_service(text)
            time_pref = "next_week" if "next week" in text else "soon"
            return IntentV1(
                verb=VerbV1.BOOK_APPOINTMENT,
                object=service,
                params={"service_type": service, "time_preference": time_pref},
                confidence=0.75,
                routine_key=f"BOOK_APPOINTMENT:{service}",
                clarifications=[],
            )

        # Reorder (default)
        items = _extract_items(text)
        if items:
            return IntentV1(
                verb=VerbV1.REORDER,
                object="items",
                params={"items": items},
                confidence=0.8,
                routine_key="REORDER:ITEMS",
                clarifications=[],
            )

        return IntentV1(
            verb=VerbV1.REORDER,
            object="usual",
            params={"usual": True},
            confidence=0.85,
            routine_key="REORDER:USUAL",
            clarifications=[],
        )


def _extract_subscription_name(text: str) -> str:
    m = re.search(r"\bcancel\s+([a-z0-9][a-z0-9\s\-]{0,40})", text)
    if not m:
        return ""
    name = m.group(1).strip()
    name = re.sub(r"\b(subscription|plan)\b", "", name).strip()
    return name.title()


def _extract_service(text: str) -> str:
    if any(k in text for k in ("clean", "cleaner", "cleaning")):
        return "cleaning"
    if any(k in text for k in ("facial", "spa")):
        return "facial"
    if any(k in text for k in ("restaurant", "dinner", "resy")):
        return "restaurant"
    return "appointment"


def _extract_items(text: str) -> list[dict[str, object]]:
    # Very small deterministic parser for a few common household nouns.
    catalog = [
        "paper towels",
        "detergent",
        "pet food",
    ]

    items: list[dict[str, object]] = []
    for name in catalog:
        if name in text:
            # Try to find a quantity immediately before the item name.
            qty = 1
            m = re.search(rf"(\d+)\s+{re.escape(name)}", text)
            if m:
                try:
                    qty = max(1, int(m.group(1)))
                except ValueError:
                    qty = 1
            items.append({"name": name, "quantity": qty})

    return items
