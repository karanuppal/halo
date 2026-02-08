from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.api.app.models.order import OrderItemInput, OrderItemPriced


@dataclass(frozen=True, slots=True)
class DraftResult:
    items: list[OrderItemPriced]
    estimated_total_cents: int
    delivery_window: str
    payment_method_masked: str
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class ExecuteResult:
    receipt_id: str
    total_cents: int
    summary: str


class AmazonAdapter(Protocol):
    vendor: str

    def build_draft(self, household_id: str, items: list[OrderItemInput]) -> DraftResult: ...

    def execute(
        self,
        household_id: str,
        items: list[OrderItemPriced],
        expected_total_cents: int,
    ) -> ExecuteResult: ...
