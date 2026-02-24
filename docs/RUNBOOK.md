# Halo MVP Runbook (Local + Dogfood)

Last updated: 2026-02-24

This runbook is the practical, copy-paste guide to run and test Halo end-to-end.

## Prereqs

- macOS with Xcode installed (for iOS + iMessage)
- `uv` installed
- Playwright Chromium installed for real Amazon/Resy browser automation

Repo:

```bash
cd /Users/karanuppal/Downloads/workspaces/halo
```

## Backend Setup

Install deps:

```bash
uv sync --group dev
uv sync --group amazon
uv run playwright install chromium
```

Seed local DB (SQLite default at `.local/halo.db`):

```bash
uv run python scripts/seed_data.py --household-id hh-1 --user-1 u-1 --user-2 u-2
```

Run API:

```bash
uv run uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health:

```bash
curl -sS http://127.0.0.1:8000/health
```

## Backend Test Gate

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## LLM Intent Extraction (OpenAI)

Default extractor is deterministic fake.

For real intent extraction:

```bash
export HALO_LLM_PROVIDER=openai
export OPENAI_API_KEY="..."
export HALO_LLM_MODEL="gpt-4o-mini"  # optional
```

Sanity check:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command/parse \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"We are low on paper towels and detergent, handle it like last time."}'
```

## Canonical REORDER (Amazon Playwright)

### 1) Link Amazon session (one-time per household)

```bash
export HALO_AMAZON_STORAGE_STATE_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_sessions"
uv run python scripts/amazon_link.py --household-id hh-1
```

### 2) Configure adapter

```bash
export HALO_AMAZON_ADAPTER=browser
export HALO_AMAZON_ARTIFACTS_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_artifacts"
```

Dry run (safe, no spend):

```bash
export HALO_AMAZON_DRY_RUN=true
```

Real spend (places order):

```bash
export HALO_AMAZON_DRY_RUN=false
```

### 3) Draft -> Confirm

Create draft from natural language (`order` and `reorder` both map to REORDER):

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"reorder the usual"}'
```

Confirm draft:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/draft/confirm \
  -H 'content-type: application/json' \
  -d '{"draft_id":"<draft_id>","user_id":"u-1"}'
```

## CANCEL SUBSCRIPTION (Mock)

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"cancel Netflix"}'
```

Confirm with `/v1/draft/confirm`.

## BOOK APPOINTMENT (Resy Dogfood Mode)

### 1) Link Resy session (one-time per household)

```bash
export HALO_RESY_STORAGE_STATE_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/resy_sessions"
uv run python scripts/resy_link.py --household-id hh-1
```

### 2) Configure adapter

```bash
export HALO_BOOKING_ADAPTER=resy
export HALO_RESY_VENUE_URL="https://resy.com/cities/new-york-ny/venues/lilia"
export HALO_RESY_VENUE_NAME="Lilia"
export HALO_RESY_ARTIFACTS_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/resy_artifacts"
```

Safe dry run (default):

```bash
export HALO_RESY_DRY_RUN=true
```

Real booking attempt:

```bash
export HALO_RESY_DRY_RUN=false
```

### 3) Create booking draft

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"book dinner Friday around 7pm for 2 at Lilia"}'
```

### 4) Modify selected time window (optional)

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/draft/modify \
  -H 'content-type: application/json' \
  -d '{"draft_id":"<draft_id>","modifications":{"selected_time_window_index":1}}'
```

### 5) Confirm booking

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/draft/confirm \
  -H 'content-type: application/json' \
  -d '{"draft_id":"<draft_id>","user_id":"u-1"}'
```

Notes:
- If availability is blocked (not logged in, GDA gate, anti-bot, or no inventory), adapter fails closed with artifact paths under `.local/resy_artifacts/...`.
- Real mode can still fail safely if final confirmation controls are uncertain.

## Draft Rehydration Endpoint (for iMessage)

Fetch a previously created draft card:

```bash
curl -sS http://127.0.0.1:8000/v1/drafts/<draft_id>
```

## Audit APIs

List executions:

```bash
curl -sS 'http://127.0.0.1:8000/v1/executions?household_id=hh-1'
```

Execution detail:

```bash
curl -sS 'http://127.0.0.1:8000/v1/executions/<execution_id>'
```

Receipts:

```bash
curl -sS 'http://127.0.0.1:8000/v1/receipts/<execution_id>'
```

## iOS App + iMessage Extension

Generate project:

```bash
cd /Users/karanuppal/Downloads/workspaces/halo/apps/ios
xcodegen generate
```

Check simulator runtimes:

```bash
xcodebuild -showsdks | grep -i Simulator
xcrun simctl list runtimes
```

Build app:

```bash
xcodebuild -project Halo.xcodeproj -scheme HaloApp \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build
```

Run UI smoke tests:

```bash
xcodebuild -project Halo.xcodeproj -scheme HaloApp \
  -destination 'platform=iOS Simulator,name=iPhone 16 Pro' test
```

If build/test fails with an iOS platform error, install the required iOS platform/runtime in:
- Xcode -> Settings -> Components

Manual extension flow:
- Open Messages in iOS Simulator.
- Open the Halo extension.
- Submit command -> review draft -> modify/confirm.
- Send card to thread.
- Tap the sent card bubble to rehydrate state from backend (`draft_id` / `execution_id`).


## Unsupported Request Check

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command   -H 'content-type: application/json'   -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"fix kitchen sink"}'
```

Expected: card with `type=UNSUPPORTED` and supported verbs list.


## Autopilot Telemetry Check

After confirm, Halo logs `AUTOPILOT_SIGNAL_COMPUTED` rows in `event_log`.

```bash
sqlite3 .local/halo.db "select event_type, json_extract(event_payload_json, '$.routine_key'), json_extract(event_payload_json, '$.repeats_count') from event_log where event_type='AUTOPILOT_SIGNAL_COMPUTED' order by created_at desc limit 5;"
```

This is learning-only telemetry (no autonomous execution in MVP).
