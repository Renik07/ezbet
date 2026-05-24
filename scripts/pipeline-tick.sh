#!/bin/sh

set -eu

BASE_URL="${EZBET_API_BASE_URL:-http://localhost:8000}"
FORCE="${PIPELINE_MODE:-tick}"

post_step() {
  STEP_NAME="$1"
  PATH_SUFFIX="$2"
  TARGET_URL="${BASE_URL%/}${PATH_SUFFIX}"

  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${STEP_NAME}: POST ${TARGET_URL}"
  curl -sS -X POST "$TARGET_URL" \
    -H "Content-Type: application/json" \
    -d '{}'
  echo
}

case "$FORCE" in
  tick)
    INGEST_PATH="/api/v1/scheduler/tick"
    ENRICHMENT_PATH="/api/v1/enrichment-scheduler/tick"
    EDITORIAL_PATH="/api/v1/editorial-scheduler/tick"
    PUBLISH_PATH="/api/v1/publish-scheduler/tick"
    ;;
  run)
    INGEST_PATH="/api/v1/scheduler/run"
    ENRICHMENT_PATH="/api/v1/enrichment-scheduler/run"
    EDITORIAL_PATH="/api/v1/editorial-scheduler/run"
    PUBLISH_PATH="/api/v1/publish-scheduler/run"
    ;;
  *)
    echo "Unsupported PIPELINE_MODE: $FORCE" >&2
    exit 1
    ;;
esac

post_step "INGEST" "$INGEST_PATH"
post_step "ENRICHMENT" "$ENRICHMENT_PATH"
post_step "EDITORIAL" "$EDITORIAL_PATH"
post_step "PUBLISH" "$PUBLISH_PATH"
