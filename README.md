# Halo MVP

This repo contains the Halo MVP backend and (soon) iOS clients.

## Local Setup (Backend)

### 1) Install deps

```bash
cd /Users/karanuppal/Downloads/workspaces/halo
uv sync --group dev
```

### 2) (Optional) Install Playwright for real Amazon browser automation

```bash
uv sync --group amazon
uv run playwright install chromium
```

### 3) Seed local DB (recommended)

Defaults to SQLite at `.local/halo.db`.

```bash
uv run python scripts/seed_data.py --household-id hh-1 --user-1 u-1 --user-2 u-2
```

### 4) Run API

```bash
uv run uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Health:

```bash
curl -sS http://127.0.0.1:8000/health
```

## LLM Intent Extraction

By default, the backend uses a deterministic fake intent extractor.

To use OpenAI:

```bash
export HALO_LLM_PROVIDER=openai
export OPENAI_API_KEY="..."
export HALO_LLM_MODEL="gpt-4o-mini"   # optional
```

## Amazon REORDER (Canonical)

### Link a household session (required for `HALO_AMAZON_ADAPTER=browser`)

```bash
export HALO_AMAZON_STORAGE_STATE_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_sessions"
uv run python scripts/amazon_link.py --household-id hh-1
```

### Run in dry-run (stops at checkout)

```bash
export HALO_AMAZON_ADAPTER=browser
export HALO_AMAZON_DRY_RUN=true
export HALO_AMAZON_ARTIFACTS_DIR="/Users/karanuppal/Downloads/workspaces/halo/.local/amazon_artifacts"
```

### Real order (spends money)

```bash
export HALO_AMAZON_ADAPTER=browser
export HALO_AMAZON_DRY_RUN=false
```

## MVP API Usage

### 1) Submit a natural-language command (returns a Draft card)

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"reorder the usual"}'
```

Other examples:

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"cancel Netflix"}'

curl -sS -X POST http://127.0.0.1:8000/v1/command \
  -H 'content-type: application/json' \
  -d '{"household_id":"hh-1","user_id":"u-1","raw_command_text":"book cleaner next week"}'
```

If the response is `CLARIFY`, answer the question(s) by resubmitting with `clarification_answers`.

### 2) Modify a draft (no spend)

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/draft/modify \
  -H 'content-type: application/json' \
  -d '{"draft_id":"<draft_id>","modifications":{"selected_time_window_index":1}}'
```

### 3) Confirm a draft (spend / irreversible boundary)

```bash
curl -sS -X POST http://127.0.0.1:8000/v1/draft/confirm \
  -H 'content-type: application/json' \
  -d '{"draft_id":"<draft_id>","user_id":"u-1"}'
```

### 4) Audit APIs

```bash
curl -sS 'http://127.0.0.1:8000/v1/executions?household_id=hh-1'
curl -sS 'http://127.0.0.1:8000/v1/executions/<execution_id>'
curl -sS 'http://127.0.0.1:8000/v1/receipts/<execution_id>'
```

## Tests

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Key Docs

- Governance: `AGENTS.md`
- Plan: `docs/PLAN.md`
- Acceptance checklist: `docs/ACCEPTANCE.md`
- Amazon browser integration: `docs/amazon_browser.md`
