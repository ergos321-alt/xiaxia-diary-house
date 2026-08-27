#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DIARY_BASE_URL:-}" || -z "${DIARY_API_TOKEN:-}" ]]; then
  echo "Set DIARY_BASE_URL and DIARY_API_TOKEN before running this deployed smoke test." >&2
  exit 2
fi

base_url="${DIARY_BASE_URL%/}"
auth_header="Authorization: Bearer ${DIARY_API_TOKEN}"

curl --fail --silent --show-error "${base_url}/healthz"
recent_json="$(curl --fail --silent --show-error -H "$auth_header" "${base_url}/api/diary/recent?page=1&page_size=2")"
entry_id="$(python -c '
import json, sys
payload = json.load(sys.stdin)
assert "pagination" in payload and "total" in payload["pagination"]
assert "has_more" in payload["pagination"]
assert all("content" not in entry for entry in payload["entries"])
print(payload["entries"][0]["id"] if payload["entries"] else "")
' <<< "$recent_json")"
if [[ -n "$entry_id" ]]; then
  curl --fail --silent --show-error -H "$auth_header" "${base_url}/api/diary/entries/${entry_id}"
fi
curl --fail --silent --show-error -H "$auth_header" "${base_url}/api/diary/context?per_author=1&reply_limit=1"

echo
echo "Paginated directory and complete-entry smoke checks passed."
