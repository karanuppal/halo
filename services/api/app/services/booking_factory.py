from __future__ import annotations

import os

from services.api.app.services.booking_base import BookingAdapter
from services.api.app.services.booking_mock import MockBookingAdapter


def get_booking_adapter() -> BookingAdapter:
    provider = os.getenv("HALO_BOOKING_ADAPTER", "mock").strip().lower()

    if provider in ("mock", "demo"):
        return MockBookingAdapter()

    if provider in ("resy", "resy_browser"):
        from services.api.app.services.resy_browser import ResyBrowserBookingAdapter

        return ResyBrowserBookingAdapter()

    raise ValueError(f"Unknown HALO_BOOKING_ADAPTER={provider!r}. Expected mock or resy.")
