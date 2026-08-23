#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DIARY_BASE_URL:-}" || -z "${DIARY_API_TOKEN:-}" ]]; then
  echo "Set DIARY_BASE_URL and DIARY_API_TOKEN before running this deployed smoke test." >&2
  exit 2
fi

base_url="${DIARY_BASE_URL%/}"
auth_header="Authorization: Bearer ${DIARY_API_TOKEN}"

curl --fail --silent --show-error "${base_url}/healthz"
curl --fail --silent --show-error -H "$auth_header" "${base_url}/api/diary/recent?limit=2"
curl --fail --silent --show-error -H "$auth_header" "${base_url}/api/diary/context?per_author=1&reply_limit=1"

echo
echo "Read-only deployed smoke checks passed."

