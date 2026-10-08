#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$SCRIPT_DIR/admin-env.sh"
BASE_URL="${EZBET_API_BASE_URL:-http://localhost:8000}"
TARGET_URL="${BASE_URL%/}/api/v1/guides/scheduler/run"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] GUIDES CRON: POST ${TARGET_URL}"
curl --fail-with-body -sS --max-time 900 -X POST "$TARGET_URL" \
  -H "x-admin-token: ${EZBET_ADMIN_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
echo
