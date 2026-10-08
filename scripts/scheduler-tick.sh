#!/bin/sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$SCRIPT_DIR/admin-env.sh"

BASE_URL="${EZBET_API_BASE_URL:-http://localhost:8000}"
MODE="${SCHEDULER_MODE:-tick}"

case "$MODE" in
  tick)
    PATH_SUFFIX="/api/v1/scheduler/tick"
    ;;
  run)
    PATH_SUFFIX="/api/v1/scheduler/run"
    ;;
  *)
    echo "Unsupported SCHEDULER_MODE: $MODE" >&2
    exit 1
    ;;
esac

TARGET_URL="${BASE_URL%/}${PATH_SUFFIX}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] POST ${TARGET_URL}"
curl --fail-with-body -sS --max-time 900 -X POST "$TARGET_URL" \
  -H "x-admin-token: ${EZBET_ADMIN_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
echo
