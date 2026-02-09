from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from services.api.app.models.order import OrderItemInput, OrderItemPriced


class AmazonAdapterError(Exception):
    """Base class for Amazon adapter errors."""


class AmazonLinkRequiredError(AmazonAdapterError):
    def __init__(self, storage_state_path: Path) -> None:
        super().__init__(
            f"Amazon session not linked. Create a storage_state file at: {storage_state_path}"
        )
        self.storage_state_path = storage_state_path


class AmazonPlaywrightMissingError(AmazonAdapterError):
    def __init__(self) -> None:
        super().__init__(
            "playwright is not installed. Install the optional group and browsers:\n"
            "  uv sync --group amazon\n"
            "  uv run playwright install chromium"
        )


class AmazonBotCheckError(AmazonAdapterError):
    def __init__(self, artifact_path: Path) -> None:
        super().__init__(
            "Amazon presented a bot check/captcha. Resolve it interactively and retry. "
            f"Debug artifact: {artifact_path}"
        )
        self.artifact_path = artifact_path


class AmazonCheckoutTotalDriftError(AmazonAdapterError):
    def __init__(self, expected_total_cents: int, actual_total_cents: int) -> None:
        super().__init__(
            "Checkout total drifted too far from draft estimate. "
            f"draft={expected_total_cents} actual={actual_total_cents}"
        )
        self.expected_total_cents = expected_total_cents
        self.actual_total_cents = actual_total_cents


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
