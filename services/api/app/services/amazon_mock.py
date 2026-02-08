from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from services.api.app.models.order import OrderItemInput, OrderItemPriced


@dataclass
class DraftResult:
    items: list[OrderItemPriced]
    estimated_total_cents: int
    delivery_window: str
    payment_method_masked: str
    warnings: list[str]


@dataclass
class ExecuteResult:
    receipt_id: str
    total_cents: int
    summary: str


class AmazonMockAdapter:
    vendor = "AMAZON_MOCK"

    def __init__(self) -> None:
        self._catalog = {
            "paper towels": 1299,
            "detergent": 1599,
            "pet food": 2499,
        }

    def build_draft(self, items: list[OrderItemInput]) -> DraftResult:
        priced_items: list[OrderItemPriced] = []
        total = 0
        for item in items:
            unit_price = self._catalog.get(item.name.lower(), 999)
            line_total = unit_price * item.quantity
            total += line_total
            priced_items.append(
                OrderItemPriced(
                    name=item.name,
                    quantity=item.quantity,
                    unit_price_cents=unit_price,
                    line_total_cents=line_total,
                )
            )

        return DraftResult(
            items=priced_items,
            estimated_total_cents=total,
            delivery_window="3-5 days",
            payment_method_masked="Visa •••• 4242",
            warnings=[],
        )

    def execute(self, total_cents: int) -> ExecuteResult:
        return ExecuteResult(
            receipt_id=f"amz_{uuid4().hex[:10]}",
            total_cents=total_cents,
            summary="Order placed",
        )
