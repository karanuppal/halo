from __future__ import annotations

from datetime import datetime, timedelta

from services.api.app.services.booking_base import (
    BookingAdapter,
    BookingDraftResult,
    BookingExecuteResult,
)


def _default_time_windows() -> list[dict[str, str]]:
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    base = now + timedelta(days=1)
    return [
        {
            "start": (base.replace(hour=9)).isoformat() + "Z",
            "end": (base.replace(hour=11)).isoformat() + "Z",
        },
        {
            "start": (base.replace(hour=12)).isoformat() + "Z",
            "end": (base.replace(hour=14)).isoformat() + "Z",
        },
        {
            "start": (base.replace(hour=15)).isoformat() + "Z",
            "end": (base.replace(hour=17)).isoformat() + "Z",
        },
    ]


class MockBookingAdapter(BookingAdapter):
    vendor = "MOCK_BOOKING"

    def build_draft(
        self,
        household_id: str,
        *,
        vendor_name: str,
        service_type: str,
        price_estimate_cents: int,
        params: dict,
    ) -> BookingDraftResult:
        del household_id, params

        windows = _default_time_windows()
        return BookingDraftResult(
            vendor=self.vendor,
            vendor_name=vendor_name,
            service_type=service_type,
            price_estimate_cents=price_estimate_cents,
            time_windows=windows,
            selected_time_window_index=0,
            warnings=[],
        )

    def execute(self, household_id: str, *, draft_payload: dict) -> BookingExecuteResult:
        del household_id

        confirmation_id = draft_payload.get("confirmation_id")
        if not confirmation_id:
            confirmation_id = f"book_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        service = draft_payload.get("service_type")
        vendor = draft_payload.get("vendor_name")

        idx = int(draft_payload.get("selected_time_window_index") or 0)
        windows = draft_payload.get("time_windows") or []
        selected = windows[idx] if isinstance(windows, list) and len(windows) > idx else {}

        summary = (
            f"Booked {service} with {vendor}. Confirmation: {confirmation_id}. Window: {selected}"
        )

        return BookingExecuteResult(
            confirmation_id=str(confirmation_id),
            summary=summary,
            external_reference_id=str(confirmation_id),
        )
