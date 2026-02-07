#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <commit-sha> [timeout-seconds]" >&2
  exit 2
fi

SHA="$1"
TIMEOUT="${2:-600}"
INTERVAL=10
REMOTE="origin"
BRANCH="ci-status"
END=$((SECONDS + TIMEOUT))

while [[ $SECONDS -lt $END ]]; do
  git fetch "$REMOTE" "$BRANCH" --quiet || true
  if git show "refs/remotes/${REMOTE}/${BRANCH}:status/${SHA}.json" >/dev/null 2>&1; then
    json=$(git show "refs/remotes/${REMOTE}/${BRANCH}:status/${SHA}.json")
    conclusion=$(python3 - <<PY
import json, sys
print(json.loads(sys.stdin.read()).get("conclusion", ""))
PY
<<<"$json")

    echo "$json"

    if [[ "$conclusion" == "success" ]]; then
      exit 0
    fi

    if [[ -n "$conclusion" && "$conclusion" != "success" && "$conclusion" != "neutral" ]]; then
      exit 1
    fi
  fi

  sleep "$INTERVAL"
done

echo "Timed out waiting for CI status for $SHA" >&2
exit 3
