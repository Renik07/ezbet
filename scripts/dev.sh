#!/bin/sh
set -eu

load_env_file() {
  file_path="$1"
  if [ -f "$file_path" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$file_path"
    set +a
  fi
}

cleanup() {
  if [ -n "${API_PID:-}" ]; then
    kill "$API_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

load_env_file ./.env
load_env_file ./.env.local

npm run dev:infra

STALE_API_PIDS="$(pgrep -f "uvicorn services.api.app.main:app" 2>/dev/null || true)"
if [ -n "$STALE_API_PIDS" ]; then
  echo "Stopping stale API process..."
  kill $STALE_API_PIDS >/dev/null 2>&1 || true
  sleep 1
fi

POSTGRES_CONTAINER_ID="$(docker compose ps -q postgres)"

if [ -n "$POSTGRES_CONTAINER_ID" ]; then
  echo "Waiting for PostgreSQL to become healthy..."
  while :; do
    POSTGRES_HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' "$POSTGRES_CONTAINER_ID" 2>/dev/null || echo unknown)"
    if [ "$POSTGRES_HEALTH" = "healthy" ]; then
      break
    fi
    sleep 1
  done
fi

npm run dev:api &
API_PID=$!

NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm run dev:web
