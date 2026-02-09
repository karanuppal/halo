# Halo MVP Acceptance Checklist

This checklist is owned by QA. It is the definition of done for the MVP.

## Global Constraints

- Halo never reads iMessage threads passively.
- Halo only processes user input explicitly submitted via the iMessage extension UI or API calls.
- Draft creation never spends money or commits irreversible actions.
- Confirm is the only step that can spend money or commit irreversible actions.
- Clarifications are bounded to 1 to 2 questions maximum.
- Unsupported requests return a structured unsupported response, not a chat loop.
- Every state transition is logged in an append-only event log.

## Verb: REORDER

### Backend

- Given a vague command, intent extraction returns `REORDER` with a routine_key.
- Draft includes:
  - Items and quantities
  - Estimated total
  - Delivery window (best-effort)
  - Payment method masked
  - Warnings if price unknown or ambiguous
- Confirm executes using the Amazon Playwright adapter.
- Confirm produces a receipt artifact (at minimum: receipt_id and human-readable summary).
- If checkout total drifts beyond threshold, execution stops and requires a new draft and confirm.

### Manual Regression (Amazon)

- Linking flow works (`scripts/amazon_link.py`).
- Draft succeeds for a simple item list.
- Confirm succeeds in dry-run mode (stops at checkout and writes a screenshot).
- Confirm succeeds in real mode (places an order) when explicitly enabled.
- Failures produce screenshot plus HTML artifacts.

## Verb: CANCEL_SUBSCRIPTION

### Backend

- Intent extraction returns `CANCEL_SUBSCRIPTION` for natural language cancel requests.
- Draft includes:
  - Subscription name
  - Monthly cost
  - Next renewal date
  - Irreversibility warning
- Confirm generates a cancellation confirmation artifact.
- Cancellation is idempotent (reconfirm does not create duplicate cancellations).

## Verb: BOOK_APPOINTMENT

### Backend

- Intent extraction returns `BOOK_APPOINTMENT` for natural language booking requests.
- Draft includes:
  - Service type
  - 3 time window options
  - Price estimate
  - Vendor name
- Modify flow selects one of the 3 windows.
- Confirm generates a booking confirmation artifact.
- If availability changes, execution stops and requires a new draft and confirm.

## Unsupported Requests

- A request outside the 3 verbs returns a structured unsupported response that enumerates supported verbs.

## iMessage Extension

- Command input is explicit and user-initiated.
- Draft card is rendered as structured content (not free-form bot chat).
- Confirm, Modify, Cancel actions are tappable and deterministic.
- Executing, Done, Failed states are visible in-thread.

## Audit Dashboard App

- Activity feed shows newest-first executions with:
  - Verb
  - Status
  - Timestamp
  - Cost (when applicable)
- Execution detail shows:
  - Original user command text
  - Parsed intent JSON
  - Draft parameters and final parameters
  - Confirmation latency
  - Receipt artifact
  - Error details and retry history

