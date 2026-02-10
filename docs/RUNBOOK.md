# Halo MVP Runbook (Local + Dogfood)

Last updated: 2026-02-10

This runbook is the practical, copy-paste guide to running and testing Halo end-to-end.

## Prereqs

- macOS with Xcode installed (for iOS + iMessage).
- `uv` installed.
- (Optional, for real Amazon) Playwright Chromium installed.

Repo:

```bash
cd /Users/karanuppal/Downloads/workspaces/halo
```

## Backend: Setup

Install deps:

```bash
uv sync --group dev
```

Optional (real Amazon/Resy browser automation, when enabled):

```bash
uv sync --group amazon
uv run playwright install chromium
```

Seed local DB (SQLite default at `.local/halo.db`):

```bash
uv run python scripts/seed_data.py --household-id hh-1 --user-1 u-1 --user-2 u-2
```

Run the API:

```bash
uv run uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health:

```bash
curl -sS http://127.0.0.1:8000/health
```

## Backend: Tests

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## LLM Intent Extraction (OpenAI)

By default, the backend uses a deterministic fake extractor.

To use OpenAI:

```bash
export HALO_LLM_PROVIDER=openai
export OPENAI_API_KEY="..."
export HALO_LLM_MODEL="gpt-4o-mini"  # optional
```

Sanity check:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command/parse \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"We are running low on paper towels, can you handle it like last time?"}'
```

## Amazon REORDER (Canonical)

### 1) Link Amazon session (one-time per household)

This stores Playwright `storage_state` under `.local/amazon_sessions/<household_id>/`.

```bash
export HALO_AMAZON_STORAGE_STATE_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_sessions"
uv run python scripts/amazon_link.py --household-id hh-1
```

### 2) Configure adapter and artifacts

```bash
export HALO_AMAZON_ADAPTER=browser
export HALO_AMAZON_ARTIFACTS_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_artifacts"
```

Dry run (stops at checkout, does not place order):

```bash
export HALO_AMAZON_DRY_RUN=true
```

Real spend (places order):

```bash
export HALO_AMAZON_DRY_RUN=false
```

### 3) Draft -> Confirm flow (curl)

Submit command:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"reorder the usual"}'
```

If response `type` is `CLARIFY`, resubmit with answers:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"cancel it","clarification_answers":{"q0":"Netflix"}}'
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

Confirm via `/v1/draft/confirm` using the returned `draft_id`.

## BOOK APPOINTMENT (Mock today, Resy planned)

Mock booking draft:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"book cleaner next week"}'
```

Modify booking (select window index 1):

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/draft/modify \
  -H 'content-type: application/json' \
  -d '{"draft_id":"<draft_id>","modifications":{"selected_time_window_index":1}}'
```

Confirm via `/v1/draft/confirm`.

### Resy booking (to be implemented in Milestone M4)

Design intent:
- `HALO_BOOKING_ADAPTER=resy`
- `scripts/resy_link.py --household-id hh-1` to create a household session/token under `.local/`
- Draft queries availability and returns 3 candidate time slots
- Confirm books and stores a confirmation artifact

## Audit Dashboard APIs (curl)

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

## iOS: Generate + Build (App + Messages Extension)

Generate Xcode project:

```bash
cd /Users/karanuppal/Downloads/workspaces/halo/apps/ios
xcodegen generate
```

Build (simulator):

1) Ensure an iOS Simulator runtime matching Xcode’s iOS SDK is installed:

```bash
xcodebuild -showsdks | grep -i "Simulator - iOS"
xcrun simctl list runtimes
```

If you do not see an iOS runtime that matches the `iphonesimulatorXX.Y` SDK that Xcode reports, install it in:
- Xcode -> Settings -> Components (download the iOS Simulator runtime)

2) Pick a simulator device name:

```bash
xcrun simctl list devices
```

3) Build:

```bash
xcodebuild -project Halo.xcodeproj -scheme HaloApp   -destination 'platform=iOS Simulator,name=iPhone 16 Pro' build
```

Run:
- Open the generated `Halo.xcodeproj` in Xcode.
- Select `HaloApp` target.
- Run on an iOS Simulator.

Messages extension:
- In the simulator, open Messages.
- Start a conversation.
- Tap the app drawer and add Halo.

Local backend connectivity notes:
- If the backend runs on your Mac at `127.0.0.1:8000`, the iOS simulator can reach it.
- For a physical phone, you will need a reachable host (LAN IP or Cloud Run) later.

## Final MVP Manual Test (End-to-End)

1. Start backend and seed DB.
2. Enable OpenAI LLM provider.
3. iMessage: send a verbose REORDER request.
4. Confirm Draft. Ensure Done includes receipt artifact.
5. iOS app: verify the execution appears in Activity feed and detail shows raw command + intent + receipt.
6. CANCEL: send "cancel Netflix" and confirm.
7. BOOK: once Resy adapter is implemented, run the Resy booking flow end-to-end.
