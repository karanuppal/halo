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
- Require linear history (rebase merges only)
- Restrict who can push to matching branches (disable direct pushes to main)

## Local Workflow

- Create feature branches prefixed with `codex/`
- Rebase onto `main` before merge
- No direct pushes to `main`
