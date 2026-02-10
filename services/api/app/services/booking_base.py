from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class BookingAdapterError(Exception):
    """Base class for booking adapter errors."""


class BookingLinkRequiredError(BookingAdapterError):
    def __init__(self, storage_state_path: Path) -> None:
        super().__init__(
            f"Booking session not linked. Create a storage_state file at: {storage_state_path}"
        )
        self.storage_state_path = storage_state_path


class BookingPlaywrightMissingError(BookingAdapterError):
    def __init__(self) -> None:
        super().__init__(
            "playwright is not installed. Install the optional group and browsers:\n"
            "  uv sync --group amazon\n"
            "  uv run playwright install chromium"
        )


@dataclass(frozen=True, slots=True)
class BookingDraftResult:
    vendor: str
    vendor_name: str
    service_type: str
    price_estimate_cents: int
    time_windows: list[dict[str, str]]
    selected_time_window_index: int
    warnings: list[str]


@dataclass(frozen=True, slots=True)
class BookingExecuteResult:
    confirmation_id: str
    summary: str
    external_reference_id: str | None = None


class BookingAdapter(Protocol):
    vendor: str

    def build_draft(
        self,
        household_id: str,
        *,
        vendor_name: str,
        service_type: str,
        price_estimate_cents: int,
        params: dict,
    ) -> BookingDraftResult: ...

    def execute(self, household_id: str, *, draft_payload: dict) -> BookingExecuteResult: ...
