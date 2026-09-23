#!/usr/bin/env bash
# Post-deploy smoke test (PVC-133). Fails the pipeline if the public endpoints do not behave as expected.
#
#   MCP_URL=https://mcp.staging.example.com/mcp API_URL=https://approvals.staging.example.com smoke.sh
#
# Checks:
#   1. approval API    GET  $API_URL/healthz                      -> 200 {"status":"ok"}
#   2. MCP endpoint    POST $MCP_URL (initialize, no token)        -> 401 with a Bearer WWW-Authenticate challenge
#   3. OAuth metadata  GET  /.well-known/oauth-protected-resource/mcp -> 200 naming $MCP_URL as the resource
#   4. TLS redirect    GET  http://<api host>/healthz              -> 301 to https
set -euo pipefail

: "${MCP_URL:?MCP_URL is required}"
: "${API_URL:?API_URL is required}"

CURL=(curl --silent --show-error --max-time 15 --retry 6 --retry-delay 10 --retry-all-errors)
failures=0
pass() { echo "PASS $*"; }
fail() { echo "FAIL $*" >&2; failures=$((failures + 1)); }

# 1. Approval API health
body="$("${CURL[@]}" --fail "$API_URL/healthz" || true)"
if [[ "$(jq -r '.status // empty' <<<"$body" 2>/dev/null)" == "ok" ]]; then
  pass "api /healthz -> $(jq -c . <<<"$body")"
else
  fail "api /healthz returned: ${body:-<no body>}"
fi

# 2. Unauthenticated MCP request must be rejected
headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT
init='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"pvc-smoke","version":"1"}}}'
code="$("${CURL[@]}" --output /dev/null --dump-header "$headers" --write-out '%{http_code}' \
  -X POST "$MCP_URL" -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  --data "$init" || true)"
if [[ "$code" == "401" ]] && grep -qi '^www-authenticate: *bearer' "$headers"; then
  pass "unauthenticated MCP initialize -> 401 Bearer challenge"
else
  fail "unauthenticated MCP initialize -> HTTP ${code:-none} (expected 401 with WWW-Authenticate: Bearer)"
fi

# 3. Protected-resource metadata (what MCP clients use to find the identity provider)
origin="$(sed -E 's#^(https://[^/]+).*#\1#' <<<"$MCP_URL")"
path="$(sed -E 's#^https://[^/]+##' <<<"$MCP_URL")"
meta="$("${CURL[@]}" --fail "$origin/.well-known/oauth-protected-resource$path" || true)"
resource="$(jq -r '.resource // empty' <<<"$meta" 2>/dev/null || true)"
if [[ -n "$resource" && "${resource%/}" == "${MCP_URL%/}" ]]; then
  pass "protected-resource metadata names $MCP_URL"
else
  fail "protected-resource metadata missing or wrong: ${meta:-<no body>}"
fi

# 4. Plain HTTP is redirected to HTTPS
http_url="$(sed -E 's#^https://#http://#' <<<"$API_URL")/healthz"
redirect="$("${CURL[@]}" --output /dev/null --write-out '%{http_code} %{redirect_url}' "$http_url" || true)"
if [[ "$redirect" == 301\ https://* ]]; then
  pass "http -> https redirect ($redirect)"
else
  fail "http redirect returned: ${redirect:-none}"
fi

if ((failures > 0)); then
  echo "$failures smoke check(s) failed" >&2
  exit 1
fi
echo "all smoke checks passed"
