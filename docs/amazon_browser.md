# Amazon Browser Integration (Playwright)

This is a best-effort Amazon ordering adapter implemented via Playwright.

## Local Setup

1. Install deps:

```bash
uv sync --group dev --group amazon
uv run playwright install chromium
```

2. Link an Amazon session for a household (saves cookies/session state):

```bash
uv run python scripts/amazon_link.py --household-id hh-1
```

By default this writes `./.local/amazon_sessions/hh-1.json`.

3. Start the API with the browser adapter:

```bash
export HALO_AMAZON_ADAPTER=browser
export HALO_AMAZON_STORAGE_STATE_DIR=.local/amazon_sessions
export HALO_AMAZON_ARTIFACTS_DIR=.local/amazon_artifacts

# Safety: confirm will stop at checkout by default.
export HALO_AMAZON_DRY_RUN=true

uv run uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Test With curl

Create a draft (no spend):

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/order/draft \
  -H 'content-type: application/json' \
  -d '{
    "household_id": "hh-1",
    "user_id": "u-1",
    "items": [{"name": "paper towels", "quantity": 1}]
  }'
```

Confirm (spend boundary). With `HALO_AMAZON_DRY_RUN=true`, it stops at checkout and writes a screenshot:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/order/confirm \
  -H 'content-type: application/json' \
  -d '{"draft_id": "<paste draft_id>"}'
```

To actually place an order:

```bash
export HALO_AMAZON_DRY_RUN=false
```

## Notes

- This will be brittle. Expect to iterate on selectors.
- The adapter attempts to clear your cart before adding items.
- If the checkout total differs from the draft estimate by more than
  `HALO_AMAZON_MAX_TOTAL_DRIFT_RATIO` (default 0.05), execution fails.
