from __future__ import annotations

import os
from pathlib import Path

from services.api.app.services.booking_base import (
    BookingAdapter,
    BookingDraftResult,
    BookingExecuteResult,
    BookingLinkRequiredError,
    BookingPlaywrightMissingError,
)


class ResyBrowserBookingAdapter(BookingAdapter):
    """Resy booking via Playwright browser automation.

    NOTE: This is a dogfood-only integration. CI must use the mock adapter.
    """

    vendor = "RESY_BROWSER"

    def __init__(self) -> None:
        self._base_url = os.getenv("HALO_RESY_BASE_URL", "https://resy.com").rstrip("/")
        self._storage_state_dir = Path(
            os.getenv("HALO_RESY_STORAGE_STATE_DIR", ".local/resy_sessions")
        )

    def build_draft(
        self,
        household_id: str,
        *,
        vendor_name: str,
        service_type: str,
        price_estimate_cents: int,
        params: dict,
    ) -> BookingDraftResult:
        del params

        storage_state = self._storage_state_dir / f"{household_id}.json"
        if not storage_state.exists():
            raise BookingLinkRequiredError(storage_state)

        # TODO: Implement real Resy availability lookup and return 3 actual time options.
        raise NotImplementedError(
            "Resy booking adapter is not implemented yet. "
            "(Planned: availability -> 3 slots -> confirm books.)"
        )

    def execute(self, household_id: str, *, draft_payload: dict) -> BookingExecuteResult:
        storage_state = self._storage_state_dir / f"{household_id}.json"
        if not storage_state.exists():
            raise BookingLinkRequiredError(storage_state)

        try:
            import playwright  # noqa: F401
        except Exception as e:
            raise BookingPlaywrightMissingError() from e

        # TODO: Implement booking confirmation via Playwright.
        raise NotImplementedError("Resy booking adapter is not implemented yet.")
