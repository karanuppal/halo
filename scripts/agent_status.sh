#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"

origin_url="$(git remote get-url origin 2>/dev/null || true)"
repo_slug=""

if [[ -n "${origin_url}" ]]; then
  if [[ "${origin_url}" =~ github.com[:/]+([^/]+)/([^/.]+)(\.git)?$ ]]; then
    repo_slug="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
  fi
fi

printf "Repo: %s\n" "${ROOT}"

# Collect worktrees as: path<TAB>branch
WORKTREES=()
while IFS=$'\t' read -r path branch; do
  WORKTREES+=("${path}"$'\t'"${branch}")
done < <(
  git worktree list --porcelain |
    awk '
      /^worktree / {path=$2}
      /^branch / {branch=$2; sub(/^refs\/heads\//, "", branch); print path "\t" branch}
      /^detached/ {print path "\t(detached)"}
    '
)

if [[ ${#WORKTREES[@]} -eq 0 ]]; then
  echo "No worktrees found."
  exit 0
fi

echo "Worktrees:"
for entry in "${WORKTREES[@]}"; do
  path="${entry%%$'\t'*}"
  branch="${entry#*$'\t'}"

  sb="$(git -C "${path}" status -sb | head -n1)"
  dirty_count="$(git -C "${path}" status --porcelain | wc -l | tr -d ' ')"
  if [[ "${dirty_count}" == "0" ]]; then
    dirty="clean"
  else
    dirty="DIRTY(${dirty_count})"
  fi

  last="$(git -C "${path}" log -1 --pretty=format:'%h %s (%cr)' 2>/dev/null || true)"

  printf -- "- %s [%s]\n" "${path} @ ${branch}" "${dirty}"
  printf "  %s\n" "${sb}"
  printf "  last: %s\n" "${last}"

  if command -v gh >/dev/null 2>&1 && [[ -n "${repo_slug}" ]] && [[ "${branch}" != "(detached)" ]]; then
    pr_json="$(gh pr list -R "${repo_slug}" --head "${branch}" --state all --limit 1 --json number,state,url,title 2>/dev/null || true)"
    if [[ "${pr_json}" =~ \"url\":\"([^\"]+)\" ]]; then
      pr_url="${BASH_REMATCH[1]}"
      pr_state="$(echo "${pr_json}" | sed -n 's/.*"state":"\([^"]*\)".*/\1/p')"
      pr_title="$(echo "${pr_json}" | sed -n 's/.*"title":"\([^"]*\)".*/\1/p')"
      printf "  pr: %s [%s] %s\n" "${pr_url}" "${pr_state}" "${pr_title}"
    fi
  fi

done
