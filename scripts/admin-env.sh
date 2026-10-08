#!/bin/sh
# Sourced by admin scripts. SCRIPT_DIR is supplied by the caller.
# Explicit caller overrides take precedence over the .env defaults.
ADMIN_TOKEN_OVERRIDE="${EZBET_ADMIN_API_TOKEN:-}"
ADMIN_BASE_URL_OVERRIDE="${EZBET_API_BASE_URL:-}"
ADMIN_FORECAST_URL_OVERRIDE="${EZBET_FORECAST_API_BASE_URL:-}"
if [ -f "$SCRIPT_DIR/../.env" ]; then
  set -a
  . "$SCRIPT_DIR/../.env"
  set +a
fi

if [ -n "$ADMIN_TOKEN_OVERRIDE" ]; then
  EZBET_ADMIN_API_TOKEN="$ADMIN_TOKEN_OVERRIDE"
fi
if [ -n "$ADMIN_BASE_URL_OVERRIDE" ]; then
  EZBET_API_BASE_URL="$ADMIN_BASE_URL_OVERRIDE"
fi
if [ -n "$ADMIN_FORECAST_URL_OVERRIDE" ]; then
  EZBET_FORECAST_API_BASE_URL="$ADMIN_FORECAST_URL_OVERRIDE"
fi

if [ -z "${EZBET_ADMIN_API_TOKEN:-}" ] || [ "${EZBET_ADMIN_API_TOKEN}" = '***' ]; then
  echo 'EZBET_ADMIN_API_TOKEN is required; configure it in the project .env or environment.' >&2
  exit 1
fi
