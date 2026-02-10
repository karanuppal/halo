from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Link a Resy session for Halo (Playwright storage_state)"
    )
    parser.add_argument("--household-id", required=True)
    parser.add_argument(
        "--base-url",
        default=os.getenv("HALO_RESY_BASE_URL", "https://resy.com"),
        help="Resy base URL (default: https://resy.com)",
    )
    parser.add_argument(
        "--storage-state-dir",
        default=os.getenv("HALO_RESY_STORAGE_STATE_DIR", ".local/resy_sessions"),
        help="Directory to write storage state JSON (default: .local/resy_sessions)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (not recommended for initial linking)",
    )
    parser.add_argument(
        "--slow-mo-ms",
        type=int,
        default=int(os.getenv("HALO_RESY_SLOW_MO_MS", "0")),
        help="Playwright slow motion delay in ms (default: 0)",
    )

    args = parser.parse_args()

    storage_state_dir = Path(args.storage_state_dir)
    storage_state_dir.mkdir(parents=True, exist_ok=True)

    storage_state_path = storage_state_dir / f"{args.household_id}.json"

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise SystemExit(
            "playwright is not installed. Run:\n"
            "  uv sync --group amazon\n"
            "  uv run playwright install chromium\n"
        ) from e

    base_url = args.base_url.rstrip("/")

    print("This will open a browser.")
    print("1. Sign into Resy in the browser.")
    print("2. Make sure you can see you're signed in.")
    print("3. Press Enter here to save session cookies to:")
    print(storage_state_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo_ms)
        context = browser.new_context()
        page = context.new_page()

        page.goto(base_url, wait_until="domcontentloaded")

        input()

        context.storage_state(path=str(storage_state_path))
        browser.close()

    print("Saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
