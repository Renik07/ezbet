#!/bin/sh

set -eu

BASE_URL="${EZBET_API_BASE_URL:-http://localhost:8000}"
MODE="${PIPELINE_MODE:-tick}"

case "$MODE" in
  tick)
    PATH_SUFFIX="/api/v1/pipeline/tick"
    ;;
  run)
    PATH_SUFFIX="/api/v1/pipeline/run"
    ;;
  *)
    echo "Unsupported PIPELINE_MODE: $MODE" >&2
    exit 1
    ;;
esac

TARGET_URL="${BASE_URL%/}${PATH_SUFFIX}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PIPELINE CRON: POST ${TARGET_URL}"
curl -sS -X POST "$TARGET_URL" \
  -H "Content-Type: application/json" \
  -d '{}'
echo
