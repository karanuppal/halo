# Halo MVP Technical Design Document

Status: Draft
Last updated: 2026-02-07

**Goals**
- Build a dogfoodable iMessage-first household agent for a single household with two users.
- Support explicit user-invoked digital tasks with confirmation boundaries and full auditability.
- Provide structured data capture for future autonomy without any autonomous execution in MVP.

**Non-Goals**
- No passive message reading or background scanning.
- No reminders, chore tracking, marketplaces, hiring, or IoT control.
- No autonomous suggestions or auto-run behaviors.

## Product Scope

**Supported verbs**
- `ORDER`: Place a new order on Amazon based on user-provided items.
- `REORDER`: Reorder last successful order or a saved “Usual” bundle on Amazon.
- `CANCEL`: Cancel a subscription from a mocked provider registry.
- `BOOK`: Book an appointment starting with Resy or equivalent.

**Confirmation boundary**
- No spend or irreversible action without explicit user confirmation.
- If an action cannot be reversed, the Draft must warn explicitly.

**Primary UX**
- iMessage extension provides explicit command input and quick intent buttons.
- Draft card shows plan, cost estimate, vendor, and Confirm / Modify / Cancel.
- Confirm triggers execution. On success, send Done card with receipt. On failure, send Failed card with reason and Retry.

**Secondary UX**
- iOS app shows Audit Dashboard with activity feed, execution detail, receipts, and setup.

## Architecture Overview

**Client**
- iMessage Extension: command input, draft rendering, modify flow, confirm flow.
- iOS App: activity feed, execution detail, household setup.

**Backend**
- FastAPI API service on Cloud Run.
- Worker service on Cloud Run for execution and retries.
- Cloud SQL Postgres for persistent data.
- Cloud Tasks for retry scheduling and async execution.
- Secret Manager for credentials.

**Core services**
- NLP + Intent Extraction: LLM-based, schema-constrained output, minimal clarification.
- Draft Generator: composes a Draft from intent + preferences + provider data.
- Execution Engine: adapter pattern with Amazon, Subscription, Booking.
- Event Logger: immutable event log for all state transitions.

## NLP and Intent Parsing

**Principle**
- Full natural language flexibility. No rigid rules engine. Any text length supported.

**Output schema**
- `verb`: ORDER | REORDER | CANCEL | BOOK | UNSUPPORTED
- `entities`: canonical entities extracted from the command
- `params`: normalized parameters by verb
- `missing_fields`: list of required fields not present
- `confidence`: 0.0 to 1.0

**Clarification**
- If required fields are missing or ambiguous, return a minimal clarification card with 1–3 options or a single short question.
- Clarification is not a chat experience. It is a structured follow-up with explicit choices.

## Draft Generation

**Draft contract**
- `title`, `summary`, `vendor`, `estimated_cost_cents`, `payment_method_masked`, `warnings`, `actions`.
- Includes verb-specific payload for Modify flow.

**Verb-specific Draft content**
- ORDER: item list with quantity, price range, delivery window, masked payment.
- REORDER: items from last order or Usual bundle, delivery window, masked payment.
- CANCEL: subscription name, cost, next renewal date, irreversibility warning.
- BOOK: vendor, service type, requested time window, price estimate.

## Execution and Adapters

**Amazon Adapter**
- Responsibilities: product search, item resolution, cart creation, price lookup, checkout, receipt capture.
- If search results are ambiguous, Draft requests clarification with top choices.
- Any price change after confirmation requires a new Draft and confirm.

**Subscription Adapter**
- Mock registry with subscription name, monthly cost, renewal date.
- Generates cancellation confirmation artifact on success.

**Booking Adapter**
- Starts with Resy or equivalent.
- Provides availability windows and booking confirmation.
- If final availability differs from Draft, request reconfirmation.

## Intelligent Retry Strategy

**Retry goals**
- Retries must be safe and not violate confirmation boundaries.

**Classification**
- Transient: retry with exponential backoff and jitter.
- Auth: refresh token once, then retry.
- Price or inventory change: stop and issue a revised Draft, require confirmation.
- Permanent: fail with reason.

**Retry policy**
- Max attempts: 3 for transient errors.
- Backoff: 5s, 30s, 2m, then fail.
- Every attempt is logged in `ExecutionAttempt`.

## Data Model

**Household**
Fields: `id`, `name`, `created_at`.

**User**
Fields: `id`, `household_id`, `display_name`, `created_at`.

**Preference**
Fields: `household_id`, `default_merchant`, `default_booking_vendor`, `created_at`, `updated_at`.

**ExecutionRequest**
Fields: `id`, `household_id`, `user_id`, `channel`, `raw_command_text`, `normalized_intent_json`, `created_at`.

**Draft**
Fields: `id`, `execution_request_id`, `verb`, `vendor`, `estimated_cost_cents`, `draft_payload_json`, `created_at`.

**Confirmation**
Fields: `id`, `draft_id`, `user_id`, `confirmed_at`, `confirmation_latency_ms`.

**Execution**
Fields: `id`, `draft_id`, `status`, `started_at`, `finished_at`, `final_cost_cents`, `execution_payload_json`, `error_message`.

**ExecutionAttempt**
Fields: `id`, `execution_id`, `attempt_number`, `started_at`, `finished_at`, `status`, `error_message`, `classification`, `retry_delay_ms`.

**ReceiptArtifact**
Fields: `id`, `execution_id`, `type`, `content_text`, `external_reference_id`, `created_at`.

**EventLog**
Fields: `id`, `household_id`, `user_id`, `entity_type`, `entity_id`, `event_type`, `event_payload_json`, `created_at`.

## API Endpoints

**Command and Draft**
- `POST /v1/command/parse`
- `POST /v1/draft/create`
- `POST /v1/draft/modify`
- `POST /v1/draft/confirm`

**Execution and Receipts**
- `GET /v1/executions?household_id=...`
- `GET /v1/executions/{id}`
- `GET /v1/receipts/{execution_id}`

## Card Payloads

**Draft card**
- Title: `Draft: <Intent>`
- Summary: plan and vendor
- Cost estimate or range
- Buttons: Confirm, Modify, Cancel

**Execution cards**
- Executing: progress state
- Done: receipt id and confirmation data
- Failed: reason and Retry action

## Infrastructure

**GCP**
- Cloud Run: `api` and `worker` services.
- Cloud SQL Postgres: primary database.
- Cloud Tasks: queue for executions and retries.
- Secret Manager: credentials for Amazon, Resy, LLM.
- Terraform: environment modules for dev and prod.

## Observability

- Structured logs with execution id correlation.
- EventLog as immutable audit trail.
- Metrics: success rate, retry rate, latency, cost variance.

## Security and Privacy

- No passive message reading.
- Commands only from explicit user actions.
- Confirmation required before spend or irreversible actions.
- Tokens stored in Secret Manager.

## Acceptance Tests

- REORDER flow works end-to-end with Draft, Confirm, Done, and receipt in dashboard.
- ORDER flow works end-to-end with Draft and Amazon confirmation.
- CANCEL flow works with warning and cancellation confirmation.
- BOOK flow works with Modify and booking confirmation.
- Unsupported flow returns Not supported card.

## Repo Structure

- `apps/ios/` iOS app and iMessage extension
- `services/api/` FastAPI backend
- `services/worker/` execution worker and adapters
- `packages/shared/` shared schemas and card payloads
- `db/` migrations and seed data
- `infra/terraform/` GCP infrastructure
- `docs/` design docs and notes

## Open Questions

- Amazon integration approach and available APIs for ordering.
- Resy or alternative booking provider credentials.
- LLM provider and structured output contract.
- iMessage card payload format and deep-link strategy.
