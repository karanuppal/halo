# Manual Amazon Regression Checklist

This is a manual checklist because automated tests must not place real orders.

## Pre-Reqs

- Install Playwright and Chromium:
  - `uv sync --group amazon`
  - `uv run playwright install chromium`

## Link Session

- Run: `uv run python scripts/amazon_link.py --household-id hh-1`
- Sign in in the opened browser.
- Press Enter in the terminal.
- Verify: `.local/amazon_sessions/hh-1.json` exists.

## Draft

- Start API with:
  - `HALO_AMAZON_ADAPTER=browser`
  - `HALO_AMAZON_DRY_RUN=true`
- Call draft:
  - `POST /v1/order/draft` with `paper towels`.
- Verify response contains:
  - product_url
  - unit_price_cents greater than 0

## Confirm (Dry Run)

- Call confirm.
- Verify response summary indicates dry-run.
- Verify screenshot exists under `.local/amazon_artifacts/.../checkout.png`.

## Confirm (Real)

- Restart API with:
  - `HALO_AMAZON_DRY_RUN=false`
  - Prefer headful: `HALO_AMAZON_HEADLESS=false`
- Call draft and then confirm.
- Verify order appears in Amazon "Your Orders".
- Verify confirmation screenshot exists under `.local/amazon_artifacts/.../confirmation.png`.

## Failure Artifacts

- If any step fails, verify:
  - `.png` screenshot exists
  - `.html` page source exists

