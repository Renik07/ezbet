#!/bin/sh

set -eu

if [ -f ./.env ]; then
  set -a
  . ./.env
  set +a
fi

BASE_URL="${EZBET_FORECAST_API_BASE_URL:-http://localhost:8000}"
ADMIN_TOKEN="${EZBET_ADMIN_API_TOKEN:-}"
TARGET_URL="${BASE_URL%/}/api/v1/forecasts/daily-run"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] POST ${TARGET_URL}"
curl --fail-with-body -sS --max-time 900 \
  --retry 2 \
  --retry-delay 60 \
  --retry-all-errors \
  -X POST "$TARGET_URL" \
  -H "x-admin-token: ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
echo
