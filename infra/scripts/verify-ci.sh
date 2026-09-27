#!/usr/bin/env bash
# Fail closed unless the most recent main push CI run for this exact SHA succeeded.
set -euo pipefail
: "${GITHUB_REPOSITORY:?required}"
: "${GITHUB_SHA:?required}"
for ((attempt=0; attempt<60; attempt++)); do
  run="$(gh api "repos/$GITHUB_REPOSITORY/actions/workflows/ci.yml/runs?head_sha=$GITHUB_SHA&event=push&branch=main&per_page=100" \
    --jq '.workflow_runs | sort_by(.id) | last')"
  if [[ "$run" != null ]]; then
    [[ "$(jq -r .head_sha <<<"$run")" == "$GITHUB_SHA" ]] || exit 1
    if [[ "$(jq -r .status <<<"$run")" == completed ]]; then
      [[ "$(jq -r .conclusion <<<"$run")" == success ]] || { echo 'Exact-SHA CI failed' >&2; exit 1; }
      echo "Verified CI run $(jq -r .id <<<"$run") for $GITHUB_SHA"
      exit 0
    fi
  fi
  sleep 30
done
echo 'No successful exact-SHA CI run within 30 minutes' >&2
exit 1
