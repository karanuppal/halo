# CI and Branch Protection

This repo uses GitHub Actions for linting, formatting, and tests. CI runs on:
- Pull requests
- Pushes to main

## Required Branch Protection (manual setup)

In GitHub repo settings:
- Settings → Branches → Add rule for `main`
- Require a pull request before merging
- Require status checks to pass before merging:
  - `CI / lint-format-test`
- Require linear history
- Restrict who can push to matching branches (disable direct pushes to main)

Merge settings (Settings → General → Pull Requests):
- Disable merge commits
- Enable squash merge (1 commit per PR)
- Disable rebase merge (optional, if you want to enforce 1 commit per PR)
- Enable auto-merge
- Enable auto-delete branches after merge
- Enable “Always suggest updating pull request branches”

## Automation

### Auto PR Creation + Auto Merge

A workflow auto-creates a PR for any branch matching `codex/**` and enables auto-merge (squash) once checks pass.

Required repo setting:
- Settings → Actions → General → Workflow permissions
  - Allow GitHub Actions to create and approve pull requests

## Local Pre-Push CI

A pre-push hook runs lint, format check, and tests locally to reduce CI failures.

Hook setup (already configured in this repo):
- `.githooks/pre-push`
- `git config core.hooksPath .githooks`

If you clone the repo elsewhere, run:

```bash
git config core.hooksPath .githooks
```

## Local Dev (uv)

- Install deps: `uv sync --group dev`
- Lint: `uv run ruff check .`
- Format check: `uv run ruff format --check .`
- Tests: `uv run pytest`
