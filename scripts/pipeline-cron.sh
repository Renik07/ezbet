#!/bin/sh

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
. "$SCRIPT_DIR/admin-env.sh"

BASE_URL="${EZBET_API_BASE_URL:-http://localhost:8000}"
MODE="${PIPELINE_MODE:-run}"

case "$MODE" in
  tick)
    PATH_SUFFIX="/api/v1/pipeline/queue?force=false"
    ;;
  run)
    PATH_SUFFIX="/api/v1/pipeline/queue?force=true"
    ;;
  *)
    echo "Unsupported PIPELINE_MODE: $MODE" >&2
    exit 1
    ;;
esac

TARGET_URL="${BASE_URL%/}${PATH_SUFFIX}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PIPELINE CRON: POST ${TARGET_URL}"
curl --fail-with-body -sS --max-time 900 -X POST "$TARGET_URL" \
  -H "x-admin-token: ${EZBET_ADMIN_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{}'
echo
