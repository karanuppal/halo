from __future__ import annotations

import os

from services.api.app.services.amazon_base import AmazonAdapter
from services.api.app.services.amazon_mock import AmazonMockAdapter


def get_amazon_adapter() -> AmazonAdapter:
    """Select an adapter based on env vars.

    Defaults to the mock adapter so tests and local dev are deterministic unless explicitly
    configured otherwise.
    """

    mode = os.getenv("HALO_AMAZON_ADAPTER", "mock").strip().lower()

    if mode == "mock":
        return AmazonMockAdapter()

    if mode == "browser":
        from services.api.app.services.amazon_browser import AmazonBrowserAdapter

        return AmazonBrowserAdapter.from_env()

    raise ValueError(f"Unknown HALO_AMAZON_ADAPTER={mode!r}. Expected mock or browser.")
