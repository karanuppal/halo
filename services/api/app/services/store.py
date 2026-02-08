from __future__ import annotations

from dataclasses import dataclass

from services.api.app.models.order import OrderDraftRequest, OrderDraftResponse


@dataclass
class DraftRecord:
    request: OrderDraftRequest
    response: OrderDraftResponse


class InMemoryStore:
    def __init__(self) -> None:
        self._drafts: dict[str, DraftRecord] = {}

    def save_draft(self, record: DraftRecord) -> None:
        self._drafts[record.response.draft_id] = record

    def get_draft(self, draft_id: str) -> DraftRecord | None:
        return self._drafts.get(draft_id)


store = InMemoryStore()
