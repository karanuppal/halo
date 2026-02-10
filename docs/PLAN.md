# Halo MVP Plan (End-to-End)

Last updated: 2026-02-10

This is the concrete, ordered build plan for finishing the Halo MVP end-to-end. It is designed to ship vertical slices, preserve the canonical Amazon + Playwright REORDER execution path, and keep CI green.

## Current State Snapshot

Backend (FastAPI) exists and is tested:
- Natural language -> Draft card -> Modify -> Confirm -> Execution -> Receipts -> Audit APIs.
- LLM intent extraction is implemented with provider switch:
  - Deterministic fake provider (default, used in tests).
  - OpenAI provider (`HALO_LLM_PROVIDER=openai`, `OPENAI_API_KEY=...`) for real intent understanding.
- Canonical REORDER integration exists:
  - Amazon browser automation via Playwright (`HALO_AMAZON_ADAPTER=browser`).
  - Spend boundary enforced via `HALO_AMAZON_DRY_RUN=true|false`.
  - Debug artifacts written on failures.

iOS exists as source scaffolding:
- `apps/ios/project.yml` exists (XcodeGen).
- SwiftUI app + Messages extension sources exist, but are not yet build-verified.

Infra (Terraform) exists as scaffolding:
- Cloud Run + Cloud SQL + secrets modules exist.
- Deployment is deferred until local dogfooding is stable.

## MVP Definition of Done

The MVP is done when:
- A user can type a vague or verbose instruction in iMessage.
- Halo (via OpenAI LLM) extracts intent, asks at most 1-2 clarifying questions if required, then produces a Draft.
- Confirm is the only spend/irreversible boundary.
- REORDER executes via the existing Amazon Playwright path (manual dogfood mode; never in CI).
- BOOK executes against a real booking system (Resy or equivalent) in dogfood mode, with a deterministic mock in CI.
- CANCEL remains deterministic mock (acceptable for MVP).
- Every action is visible in the Audit Dashboard with receipts and a full execution record.

## Milestones (Ordered)

### M0: Plan + Runbook Baseline

Deliverables:
- Update this plan to reflect the true remaining work.
- Add `docs/RUNBOOK.md` (kept up-to-date as we implement).

Testing:
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest`

### M1: iOS Project Generation + Build (Unblock iOS Work)

Goal:
- Make `apps/ios/` buildable via XcodeGen + `xcodebuild`.

Deliverables:
- `xcodegen generate` produces an Xcode project.
- `xcodebuild ... build` succeeds for the iOS app and embeds the Messages extension.
- Add minimal helper commands (repo root `Makefile` or `scripts/ios_*.sh`) for:
  - generate
  - build
  - test

Testing:
- `cd apps/ios && xcodegen generate`
- `xcodebuild ... build` (iOS Simulator)

### M2: Audit Dashboard App (Trust UI) + XCUITest Smoke

Goal:
- The iOS app shows the Activity feed and Execution detail, backed by the audit APIs.

Deliverables:
- Setup view persists base URL + household id + user id.
- Activity feed displays newest-first executions.
- Execution detail shows:
  - raw command
  - normalized intent JSON
  - draft payload vs execution payload
  - confirmation latency
  - receipt artifact(s)
- Add XCUITest smoke:
  - App launches.
  - Activity screen renders (stubbed backend by default).

Testing:
- `xcodebuild ... test` (simulator)
- Backend tests remain covered by `pytest`.

### M3: iMessage Extension MVP UX (Delegate -> Approve -> Done)

Goal:
- Messages extension can submit a command, render Draft/Clarify/Unsupported, support Modify per verb, Confirm, and render Done/Failed.

Deliverables:
- Draft rendering:
  - title/summary/vendor/estimated cost
  - Confirm / Modify / Cancel
- Modify UI:
  - REORDER: +/- quantities for 3-10 items
  - CANCEL: subscription dropdown
  - BOOK: pick from 3 time windows
- Message payload strategy:
  - insert an `MSMessage` with a deep link containing `draft_id`/`execution_id` so the app can rehydrate state.

Testing:
- Manual testing in iMessage simulator/device.
- Unit tests for message payload encode/decode where feasible.

### M4: Real Booking Integration (Resy) Behind an Adapter

Goal:
- BOOK_APPOINTMENT uses a real integration for dogfooding, while CI uses a deterministic mock.

Deliverables:
- Booking adapter interface + factory:
  - `HALO_BOOKING_ADAPTER=mock|resy`
- Resy integration (dogfood mode):
  - Draft:
    - query availability and return 3 time options
    - include vendor info and best-effort price estimate
  - Confirm:
    - book selected slot
    - store confirmation as a receipt artifact
  - Auth/link flow:
    - `scripts/resy_link.py --household-id hh-1`
    - persist session/token safely under `.local/` (never commit)
  - Preferences:
    - store default Resy venue/provider identifiers per household
- Safety guardrails:
  - fail closed if booking requires payment/deposit we cannot safely handle
  - cap retries, avoid double-booking

Testing:
- CI and automated tests must not hit Resy.
- Unit tests cover adapter contract + mock adapter.
- Manual dogfood flow documented in `docs/RUNBOOK.md`.

### M5: Intelligent Retries + Attempt Logging

Goal:
- Reduce flaky automation failures without risking double charges/reservations.

Deliverables:
- Add attempt logging (event log + optional DB table) and cap retries.
- Retry only clearly safe, pre-commit steps.
- If state is uncertain, stop and require a new Draft + Confirm.

Testing:
- Unit tests for retry classification/caps.
- Manual Amazon/Resy regressions include at least one induced transient failure.

### M6: Deployment Readiness (GCP Last)

Goal:
- Fully deployable to Cloud Run + Cloud SQL via Terraform, after local dogfooding is stable.

Deliverables:
- Postgres migrations (Alembic) for Cloud SQL.
- Terraform envs produce:
  - Cloud SQL Postgres
  - Cloud Run service(s)
  - Secret Manager entries (OpenAI key, Resy token/session)
- Minimal deploy steps in runbook.

Testing:
- Terraform `fmt` + `validate` locally.
- Optional staged deployment later.

## Test Scope (What We Run When)

Backend (every PR):
- `uv run ruff check .`
- `uv run ruff format --check .`
- `uv run pytest`

Backend (manual dogfood):
- Amazon real automation:
  - link session
  - draft
  - confirm dry-run
  - confirm real spend (explicit)
- Resy real booking:
  - link/auth
  - draft returns 3 real time slots
  - modify selects a slot
  - confirm books and returns confirmation artifact

iOS (every iOS milestone PR):
- `cd apps/ios && xcodegen generate`
- `xcodebuild ... build`
- `xcodebuild ... test` (app smoke; extension manual)

## Final MVP Test (End-to-End)

Acceptance checklist (must pass):
- REORDER: vague input -> Draft -> Confirm -> Done with receipt -> visible in dashboard.
- CANCEL: “cancel Netflix” -> Draft with warning -> Confirm -> Done with cancellation confirmation -> visible in dashboard.
- BOOK: “book dinner Friday around 7 for 2” -> Draft with 3 options -> Modify option 2 -> Confirm -> Done with Resy confirmation -> visible in dashboard.
- Unsupported: “fix kitchen sink” -> Unsupported card.

## Runbook

The end-to-end runbook lives in `docs/RUNBOOK.md` and is updated as milestones land.
