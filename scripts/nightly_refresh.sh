#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-https://chess-coach-api-um80.onrender.com}"
TRACKED_USERNAMES="${TRACKED_USERNAMES:-}"
ACCESS_KEY="${ACCESS_KEY:-}"
MAX_TRACKED_USERS="${MAX_TRACKED_USERS:-5}"
JOB_TIMEOUT_SECONDS="${JOB_TIMEOUT_SECONDS:-5400}"
POLL_SECONDS="${POLL_SECONDS:-20}"

if [[ -z "$ACCESS_KEY" ]]; then
  echo "ACCESS_KEY is required" >&2
  exit 2
fi

if ! [[ "$MAX_TRACKED_USERS" =~ ^[1-9][0-9]*$ ]]; then
  echo "MAX_TRACKED_USERS must be a positive integer" >&2
  exit 2
fi

if ! [[ "$JOB_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "JOB_TIMEOUT_SECONDS must be a positive integer" >&2
  exit 2
fi

if ! [[ "$POLL_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "POLL_SECONDS must be a positive integer" >&2
  exit 2
fi

command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 2; }

API_URL="${API_URL%/}"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

curl_common=(
  --silent
  --show-error
  --fail-with-body
  --retry 5
  --retry-delay 5
  --retry-all-errors
  --connect-timeout 20
  --max-time 180
)

echo "Waking Chess Coach API at $API_URL"
curl "${curl_common[@]}" "$API_URL/health" --output "$work_dir/health.json"

jq -n --arg access_key "$ACCESS_KEY" '{access_key: $access_key}' \
  | curl "${curl_common[@]}" \
      --header 'Content-Type: application/json' \
      --data-binary @- \
      "$API_URL/auth/session" \
      --output "$work_dir/session.json"

session_token="$(jq -er '.token | select(type == "string" and length > 0)' "$work_dir/session.json")"

if [[ -z "$TRACKED_USERNAMES" ]]; then
  curl "${curl_common[@]}" \
    --header "Authorization: Bearer $session_token" \
    "$API_URL/users/tracked" \
    --output "$work_dir/tracked-users.json"
  TRACKED_USERNAMES="$(jq -er '.usernames | join(",")' "$work_dir/tracked-users.json")"
fi

usernames=()
while IFS= read -r username; do
  usernames+=("$username")
done < <(
  jq -rn --arg value "$TRACKED_USERNAMES" \
    '$value | split(",") | map(gsub("^\\s+|\\s+$"; "")) | map(select(length > 0)) | unique[]'
)

if (( ${#usernames[@]} == 0 )); then
  echo "No tracked Chess.com usernames are available; complete one successful ingest first" >&2
  exit 2
fi

if (( ${#usernames[@]} > MAX_TRACKED_USERS )); then
  echo "Refusing to refresh ${#usernames[@]} users; cap is $MAX_TRACKED_USERS" >&2
  exit 2
fi

for username in "${usernames[@]}"; do
  encoded_username="$(jq -rn --arg value "$username" '$value | @uri')"
  echo "Queueing nightly refresh for $username"
  curl "${curl_common[@]}" \
    --request POST \
    --header "Authorization: Bearer $session_token" \
    "$API_URL/ingest/$encoded_username" \
    --output "$work_dir/ingest.json"

  job_id="$(jq -er '.job_id | select(type == "number")' "$work_dir/ingest.json")"
  deadline=$(( $(date +%s) + JOB_TIMEOUT_SECONDS ))

  while true; do
    curl "${curl_common[@]}" \
      --header "Authorization: Bearer $session_token" \
      "$API_URL/ingest/jobs/$job_id" \
      --output "$work_dir/job.json"

    status="$(jq -er '.status' "$work_dir/job.json")"
    case "$status" in
      completed)
        jq -r '"Completed \(.username): fetched=\(.games_fetched), analyzed=\(.games_analyzed), failed=\(.games_failed)"' \
          "$work_dir/job.json"
        break
        ;;
      failed)
        jq -r '"Refresh failed for \(.username): \(.error // "unknown error")"' "$work_dir/job.json" >&2
        exit 1
        ;;
      queued|running)
        if (( $(date +%s) >= deadline )); then
          echo "Refresh timed out for $username after ${JOB_TIMEOUT_SECONDS}s" >&2
          exit 1
        fi
        sleep "$POLL_SECONDS"
        ;;
      *)
        echo "Unexpected job status '$status' for $username" >&2
        exit 1
        ;;
    esac
  done
done

echo "Nightly refresh completed for ${#usernames[@]} user(s)"
