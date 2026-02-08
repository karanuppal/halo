from __future__ import annotations

from uuid import uuid4

from services.api.app.models.order import OrderItemInput, OrderItemPriced
from services.api.app.services.amazon_base import DraftResult, ExecuteResult


class AmazonMockAdapter:
    vendor = "AMAZON_MOCK"

    def __init__(self) -> None:
        self._catalog = {
            "paper towels": 1299,
            "detergent": 1599,
            "pet food": 2499,
        }

    def build_draft(self, household_id: str, items: list[OrderItemInput]) -> DraftResult:
        del household_id

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
                    product_url=None,
                )
            )

        return DraftResult(
            items=priced_items,
            estimated_total_cents=total,
            delivery_window="3-5 days",
            payment_method_masked="Visa **** 4242",
            warnings=[],
        )

    def execute(
        self,
        household_id: str,
        items: list[OrderItemPriced],
        expected_total_cents: int,
    ) -> ExecuteResult:
        del household_id

        computed_total = sum(item.line_total_cents for item in items)
        total = computed_total or expected_total_cents

        return ExecuteResult(
            receipt_id=f"amz_{uuid4().hex[:10]}",
            total_cents=total,
            summary="Order placed",
        )
