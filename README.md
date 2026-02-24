# Halo MVP

Halo is a home autopilot-in-training. This repo includes:
- FastAPI backend (LLM intent -> Draft/Modify/Confirm -> Execution -> Audit + autopilot telemetry logging)
- Canonical Amazon Playwright reorder adapter
- Resy Playwright booking adapter (dogfood mode)
- iOS app + iMessage extension scaffolding and integration

## Quick Start

```bash
cd /Users/karanuppal/Downloads/workspaces/halo
uv sync --group dev
uv sync --group amazon
uv run playwright install chromium
uv run python scripts/seed_data.py --household-id hh-1 --user-1 u-1 --user-2 u-2
uv run uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

## Backend Quality Gate

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
make backend.acceptance
```

## LLM Provider

Default is deterministic fake extractor.

For OpenAI:

```bash
export HALO_LLM_PROVIDER=openai
export OPENAI_API_KEY="..."
export HALO_LLM_MODEL="gpt-4o-mini"  # optional
```

## Core API Endpoints

- `POST /v1/command/parse`
- `POST /v1/command`
- `POST /v1/draft/modify`
- `POST /v1/draft/confirm`
- `GET /v1/drafts/{draft_id}`
- `GET /v1/executions?household_id=...`
- `GET /v1/executions/{id}`
- `GET /v1/receipts/{execution_id}`

## Canonical REORDER (Amazon)

```bash
export HALO_AMAZON_ADAPTER=browser
export HALO_AMAZON_STORAGE_STATE_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_sessions"
export HALO_AMAZON_ARTIFACTS_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_artifacts"
uv run python scripts/amazon_link.py --household-id hh-1
```

Dry run (safe):

```bash
export HALO_AMAZON_DRY_RUN=true
```

Real spend:

```bash
export HALO_AMAZON_DRY_RUN=false
```

## BOOK APPOINTMENT (Resy)

```bash
export HALO_BOOKING_ADAPTER=resy
export HALO_RESY_VENUE_URL="https://resy.com/cities/new-york-ny/venues/lilia"
export HALO_RESY_VENUE_NAME="Lilia"
export HALO_RESY_STORAGE_STATE_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/resy_sessions"
export HALO_RESY_ARTIFACTS_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/resy_artifacts"
uv run python scripts/resy_link.py --household-id hh-1
```

Dry run:

```bash
export HALO_RESY_DRY_RUN=true
```

Real booking attempt:

```bash
export HALO_RESY_DRY_RUN=false
```

## iOS / iMessage

Generate project:

```bash
cd apps/ios
xcodegen generate
```

Build/test:

```bash
xcodebuild -project Halo.xcodeproj -scheme HaloApp -destination 'platform=iOS Simulator,name=iPhone 16 Pro,OS=18.4' build
xcodebuild -project Halo.xcodeproj -scheme HaloApp -destination 'platform=iOS Simulator,name=iPhone 16 Pro,OS=18.4' test

# or from repo root
make ios.build
make ios.test
```

If Xcode reports a missing iOS platform/runtime, install it from Xcode Components.

## Docs

- Governance: `AGENTS.md`
- Plan: `docs/PLAN.md`
- Acceptance: `docs/ACCEPTANCE.md`
- Full runbook: `docs/RUNBOOK.md`
- Amazon details: `docs/amazon_browser.md`

## Autopilot Readiness Telemetry

After each execution (DONE or FAILED), Halo logs `AUTOPILOT_SIGNAL_COMPUTED` events in `event_log` with:
- routine repeats count
- cadence estimates
- item/cost variance
- trust signals (confirm latency, modify count)
- failure rate by adapter

These signals are logged only (no autonomous execution/suggestions in MVP).
