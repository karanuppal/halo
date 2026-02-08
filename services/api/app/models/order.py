from __future__ import annotations

from pydantic import BaseModel, Field


class OrderItemInput(BaseModel):
    name: str
    quantity: int = Field(..., ge=1)


class OrderDraftRequest(BaseModel):
    household_id: str
    user_id: str
    items: list[OrderItemInput] = Field(..., min_length=1)


class OrderItemPriced(BaseModel):
    name: str
    quantity: int
    unit_price_cents: int
    line_total_cents: int


class OrderDraftResponse(BaseModel):
    draft_id: str
    verb: str
    vendor: str
    items: list[OrderItemPriced]
    estimated_total_cents: int
    delivery_window: str
    payment_method_masked: str
    warnings: list[str]


class OrderConfirmRequest(BaseModel):
    draft_id: str


class OrderReceipt(BaseModel):
    receipt_id: str
    provider: str
    total_cents: int
    summary: str


class OrderConfirmResponse(BaseModel):
    execution_id: str
    status: str
    receipt: OrderReceipt
