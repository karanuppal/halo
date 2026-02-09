# Halo MVP: Agent Governance

This repo builds the Halo MVP end-to-end.

## Product Intent

Halo is a household autopilot-in-training:
- Executes digital household tasks only when explicitly invoked by a user.
- Requires explicit confirmation before spending money or committing irreversible actions.
- Produces structured Drafts and auditable receipts/confirmations.
- Logs structured data to enable future autonomy, but never auto-runs anything in MVP.

## Non-Goals (MVP)

Halo is not:
- A task tracker, reminders app, or chore organizer.
- A chatbot (no open-ended conversation loops).
- A smart-home / IoT controller.
- A passive message reader (no scanning iMessage threads).

## MVP Verbs (Exactly These)

Halo MVP supports exactly these execution verbs:
- `REORDER`: recurring household purchases.
  - Canonical integration: Amazon via Playwright browser automation.
  - Draft shows items, estimated cost, delivery window (best-effort), masked payment.
- `CANCEL_SUBSCRIPTION`: cancel a known subscription (mock provider allowed).
  - Draft shows subscription name, monthly cost, next renewal date, irreversibility warning.
- `BOOK_APPOINTMENT`: book with a predefined vendor (mock allowed initially).
  - Draft shows service, 3 time-window options, price estimate.

If request is outside scope: return a structured `UNSUPPORTED` response.

## Core UX Constraints

- Primary interface: iMessage app extension.
- Users type natural language (short or verbose). Halo must understand via LLM intent extraction.
- Halo may ask at most 1 to 2 clarification questions when required.
- Interaction should feel like: delegate -> approve -> done.

## Privacy & Trust

- No passive reading. Halo only processes user text explicitly submitted via:
  - iMessage extension input
  - API calls
- No contact syncing or thread scanning in MVP.

## Confirmation Boundary

- Draft creation must never spend money or commit irreversible actions.
- Confirm is the only boundary that can spend/commit.
- If execution encounters price/inventory drift, it must stop and require a new Draft plus confirm.

## Canonical Amazon Integration (Must Preserve)

The repo contains a real Amazon integration via Playwright. This must remain working and is the canonical `REORDER` execution path.

Key files:
- `services/api/app/services/amazon_browser.py`
- `scripts/amazon_link.py`
- `docs/amazon_browser.md`

Constraints:
- Do not add automated tests that place real Amazon orders.
- Add debug artifacts on failure (screenshots plus HTML) to support fast iteration.

## Logging / Auditability

Every state transition must be logged (append-only):
- command received
- intent extracted
- draft created
- modified
- confirmed
- execution started
- execution attempts and retries
- execution finished (done/failed)
- receipt artifacts

Also log autopilot readiness signals (store, do not surface in UI):
- routine_key repetitions, cadence, variance, confirmation latency, modify vs confirm, failure rate by adapter.

## Repo Workflow Guardrails

- No direct pushes to `main`.
- Feature branches are prefixed `codex/`.
- Squash merge preferred (linear PR history).
- CI must pass before merge.
- Prefer vertical slices over horizontal refactors.

## Multi-Agent Responsibilities

### Team Lead
- Maintain `AGENTS.md` as binding constraints.
- Produce and update the execution plan (see `docs/PLAN.md`).
- Ensure architecture coherence and safe spend/confirm boundaries.
- Integrate work via small PRs.

### Backend Agent
- Implement LLM-based intent extraction (schema-constrained output) plus bounded clarifications.
- Implement Draft/Modify/Confirm APIs for `REORDER`, `CANCEL_SUBSCRIPTION`, `BOOK_APPOINTMENT`.
- Preserve the Amazon Playwright flow as `REORDER` execution.
- Implement persistent DB (Postgres) plus migrations plus event log plus receipts.
- Implement retry classification logic (safe retries only).
- Unit and integration tests.

### iOS Agent
- Build iMessage extension UI (command input, quick actions, Draft card rendering, Modify flow, Confirm).
- Build Audit Dashboard app (activity feed plus execution detail plus receipts).
- Define and implement message payload encoding/decoding used by extension plus app.
- UI tests (XCUITest) for primary flows.

### Infra Agent
- Terraform for GCP: Cloud Run (api/worker), Cloud SQL Postgres, Secret Manager, networking.
- Local dev parity: documented env vars, emulators/stubs, minimal friction.
- Ensure deployment is possible without changing app code.

### QA Agent
- Own acceptance criteria and failure-mode checklist.
- Add integration tests and harnesses that validate:
  - no spend in draft
  - confirm boundary
  - bounded clarifications
  - audit log completeness
  - unsupported behavior
- Coordinate manual Amazon regression checklist.
