from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Link an Amazon session for Halo (Playwright storage_state)"
    )
    parser.add_argument("--household-id", required=True)
    parser.add_argument(
        "--base-url",
        default=os.getenv("HALO_AMAZON_BASE_URL", "https://www.amazon.com"),
        help="Amazon base URL (default: https://www.amazon.com)",
    )
    parser.add_argument(
        "--storage-state-dir",
        default=os.getenv("HALO_AMAZON_STORAGE_STATE_DIR", ".local/amazon_sessions"),
        help="Directory to write storage state JSON (default: .local/amazon_sessions)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (not recommended for initial linking)",
    )
    parser.add_argument(
        "--slow-mo-ms",
        type=int,
        default=int(os.getenv("HALO_AMAZON_SLOW_MO_MS", "0")),
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
    sign_in_url = f"{base_url}/ap/signin"

    print("This will open a browser to log into Amazon.")
    print("After you're fully logged in, press Enter here to save session to:")
    print(storage_state_path)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo_ms)
        context = browser.new_context()
        page = context.new_page()
        page.goto(sign_in_url, wait_until="domcontentloaded")

        input()

        context.storage_state(path=str(storage_state_path))
        browser.close()

    print("Saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
