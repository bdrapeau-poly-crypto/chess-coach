#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-https://chess-coach-api-um80.onrender.com}"
FRONTEND_URL="${FRONTEND_URL:-https://frontend-taupe-omega-75.vercel.app}"
ACCESS_KEY="${ACCESS_KEY:-}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
FAILED_INGEST_THRESHOLD="${FAILED_INGEST_THRESHOLD:-3}"
COACH_DAILY_TOKEN_ALERT="${COACH_DAILY_TOKEN_ALERT:-0}"

if [[ -z "$ACCESS_KEY" ]]; then
  echo "ACCESS_KEY is required" >&2
  exit 2
fi

if ! [[ "$FAILED_INGEST_THRESHOLD" =~ ^[1-9][0-9]*$ ]]; then
  echo "FAILED_INGEST_THRESHOLD must be a positive integer" >&2
  exit 2
fi

if ! [[ "$COACH_DAILY_TOKEN_ALERT" =~ ^[0-9]+$ ]]; then
  echo "COACH_DAILY_TOKEN_ALERT must be a non-negative integer" >&2
  exit 2
fi

command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

API_URL="${API_URL%/}"
FRONTEND_URL="${FRONTEND_URL%/}"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

curl_common=(
  --silent
  --show-error
  --fail-with-body
  --retry 5
  --retry-delay 10
  --retry-all-errors
  --connect-timeout 20
  --max-time 180
)

curl "${curl_common[@]}" "$API_URL/health" --output "$work_dir/health.json"
jq -e '.status == "ok"' "$work_dir/health.json" >/dev/null

if [[ -n "$EXPECTED_COMMIT" ]]; then
  deployed_commit="$(jq -r '.commit // empty' "$work_dir/health.json")"
  if [[ "$deployed_commit" != "$EXPECTED_COMMIT" ]]; then
    echo "Render commit mismatch: expected $EXPECTED_COMMIT, deployed ${deployed_commit:-missing}" >&2
    exit 1
  fi
fi

curl "${curl_common[@]}" "$API_URL/health/stockfish" --output "$work_dir/stockfish.json"
jq -e '.status == "ok" and .probe == true' "$work_dir/stockfish.json" >/dev/null

curl "${curl_common[@]}" "$FRONTEND_URL" --output /dev/null

curl "${curl_common[@]}" "$API_URL/auth/session" --output "$work_dir/auth-status.json"
jq -e '.auth_required == false and .authenticated == true' "$work_dir/auth-status.json" >/dev/null

jq -n --arg access_key "$ACCESS_KEY" '{access_key: $access_key}' \
  | curl "${curl_common[@]}" \
      --header 'Content-Type: application/json' \
      --data-binary @- \
      "$API_URL/auth/session" \
      --output "$work_dir/session.json"

session_token="$(jq -er '.token | select(type == "string" and length > 0)' "$work_dir/session.json")"
curl "${curl_common[@]}" \
  --header "Authorization: Bearer $session_token" \
  "$API_URL/metrics/summary?days=1" \
  --output "$work_dir/metrics.json"

if ! jq -e '.ai_budget.remaining_usd > 0' "$work_dir/metrics.json" >/dev/null; then
  echo "Daily AI coach budget is exhausted or unavailable" >&2
  exit 1
fi

failed_ingests="$(
  jq '[.events[] | select(.event_type == "ingest" and .status == "failed") | .count] | add // 0' \
    "$work_dir/metrics.json"
)"
if (( failed_ingests >= FAILED_INGEST_THRESHOLD )); then
  echo "Repeated ingest failures: $failed_ingests in the last day (threshold $FAILED_INGEST_THRESHOLD)" >&2
  exit 1
fi

coach_tokens="$(
  jq '[.events[] | select(.event_type == "coach") | (.input_tokens + .output_tokens)] | add // 0' \
    "$work_dir/metrics.json"
)"
if (( COACH_DAILY_TOKEN_ALERT > 0 && coach_tokens >= COACH_DAILY_TOKEN_ALERT )); then
  echo "Daily coach tokens: $coach_tokens (threshold $COACH_DAILY_TOKEN_ALERT)" >&2
  exit 1
fi

ai_budget_remaining="$(jq -r '.ai_budget.remaining_usd' "$work_dir/metrics.json")"
echo "Production healthy: commit=${EXPECTED_COMMIT:-unchecked}, failed_ingests=$failed_ingests, coach_tokens=$coach_tokens, ai_budget_remaining_usd=$ai_budget_remaining"
