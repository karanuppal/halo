# Halo MVP Plan (Phase 0 Inventory and Roadmap)

Last updated: 2026-02-09

This document is the working plan owned by the Team Lead. It is intentionally concrete and ordered.

## Phase 0: Inventory (Current Repo State)

### What exists and works today

Backend (FastAPI):
- `GET /health`
- `POST /v1/order/draft`
- `POST /v1/order/confirm`

Amazon integrations:
- `AMAZON_MOCK`: deterministic mock draft and confirm for tests.
- `AMAZON_BROWSER` (Playwright): real Amazon browser automation.
  - `scripts/amazon_link.py` links a household session via Playwright `storage_state`.
  - Draft searches Amazon and reads best-effort prices.
  - Confirm clears cart, adds items, proceeds to checkout.
  - Spend boundary controlled by `HALO_AMAZON_DRY_RUN`.
  - Writes debug artifacts (screenshot + HTML) on failures.

Tests and tooling:
- `uv` dependency management (`pyproject.toml`, `uv.lock`).
- CI runs `ruff check`, `ruff format --check`, `pytest`.

Infra scaffolding:
- `infra/terraform/**` exists but is placeholder content.

iOS scaffolding:
- `apps/ios/HaloApp/.gitkeep`, `apps/ios/HaloMessagesExtension/.gitkeep` only.

### Major gaps vs MVP

Product requirements not implemented yet:
- LLM-based intent extraction for natural language commands.
- Unified draft/modify/confirm flow for the three MVP verbs.
- Bounded clarifications (1 to 2 questions max).
- Persistent Postgres-backed data model (households, users, drafts, confirmations, executions, receipts, append-only event log).
- Audit APIs for activity feed and execution detail.
- CANCEL_SUBSCRIPTION adapter (mock provider registry).
- BOOK_APPOINTMENT adapter (mock vendor, 3 time windows).
- Retry engine with safe classification.
- iMessage extension UI and Audit Dashboard iOS app.
- Terraform for Cloud Run + Cloud SQL + secrets.

## Phase 1: Backend Vertical Slice (Dogfoodable Without iOS)

Goal: From a single endpoint, accept natural language, return a structured Draft, allow Confirm, execute Amazon REORDER via Playwright, persist an audit record with receipt artifacts.

Deliverables:
- New endpoints (names may evolve, but functionality is required):
  - `POST /v1/command/parse` (LLM intent extraction)
  - `POST /v1/draft/create`
  - `POST /v1/draft/modify`
  - `POST /v1/draft/confirm`
  - `GET /v1/executions?household_id=...`
  - `GET /v1/executions/{id}`
  - `GET /v1/receipts/{execution_id}`
- Postgres schema + migrations:
  - Household, User, Preference
  - ExecutionRequest, Draft, Confirmation
  - Execution, ExecutionAttempt, ReceiptArtifact
  - EventLog (append-only)
- LLM provider abstraction with a deterministic fake for tests.
- REORDER draft creation using a stored "Usual" bundle and/or last successful REORDER.
- Execution uses existing Amazon Playwright flow (canonical integration).

Notes:
- Keep automated tests from placing real Amazon orders.
- Provide a CLI helper to exercise parse/draft/confirm locally via curl.

## Phase 2: Add Remaining MVP Verbs (Mocked)

Deliverables:
- CANCEL_SUBSCRIPTION:
  - Subscription registry table seeded with a few examples.
  - Draft includes irreversibility warning.
  - Confirm generates a cancellation confirmation artifact.
- BOOK_APPOINTMENT:
  - One predefined vendor.
  - Draft includes 3 time windows.
  - Modify selects one window.
  - Confirm generates booking confirmation.

## Phase 3: iOS iMessage Extension + Audit Dashboard

Goal: Replace curl with the real user experience.

Deliverables:
- iMessage extension:
  - Command input, quick actions.
  - Render Draft card with Confirm/Modify/Cancel.
  - Modify UI per verb.
  - Execution status updates (Executing/Done/Failed).
- Audit Dashboard app:
  - Activity feed (Done/In progress/Failed).
  - Execution detail view: original command, parsed intent, draft vs final, confirmation latency, receipts, errors.

Testing:
- XCUITest for primary flows using a stubbed backend.

## Phase 4: Infrastructure (Ready to Deploy)

Deliverables:
- Terraform modules filled out for:
  - Cloud Run (api + worker)
  - Cloud SQL Postgres
  - Secret Manager
  - Networking/IAM
- Local dev guide for env vars and secret injection.

## Work Allocation (Agents)

Team Lead:
- Own Phase 0 artifacts (`AGENTS.md`, this plan).
- Drive sequencing and PR integration.

Backend Agent (highest priority first):
1. Data model + Postgres + migrations + EventLog.
2. LLM intent extraction interface + fake provider + tests.
3. Unified Draft/Confirm API with REORDER wired to Amazon Playwright.
4. CANCEL_SUBSCRIPTION + BOOK_APPOINTMENT mock adapters.
5. Retry classification + ExecutionAttempt logging.

iOS Agent:
1. Define message payload schemas shared between extension and app.
2. iMessage extension UI (Draft, Modify, Confirm, Status).
3. Audit Dashboard app (feed + detail) using backend APIs.

Infra Agent:
1. Terraform modules for Cloud Run + Cloud SQL + Secret Manager.
2. Cloud Run service configs for worker queues/retries (later).

QA Agent:
1. Acceptance checklist mapped to MVP requirements.
2. Integration test harness for backend flows.
3. Manual Amazon regression checklist (linking, draft, confirm, receipt).

