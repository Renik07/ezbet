#!/bin/sh

set -eu

INTERVAL_SECONDS="${INTERVAL_SECONDS:-60}"

while true; do
  sh "$(dirname "$0")/pipeline-tick.sh"
  sleep "$INTERVAL_SECONDS"
done
