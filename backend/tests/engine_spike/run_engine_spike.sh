#!/usr/bin/env bash
# ENG-013 engine-selection spike: run the official Meterless H-MEM and World
# Model reference test suites and conformance runners, then write a summary.
#
# Usage:
#   backend/tests/engine_spike/run_engine_spike.sh <meterless-checkout> [log-dir]
#
# <meterless-checkout> is a clone of github.com/Meterless/Meterless containing
# at least engines/hmem and engines/world-model (a sparse checkout is enough).
# The sponsor code only ever runs inside a throwaway Node container, never on
# the host; the host only reads the logs. Exit code is 0 when every step
# passed, 1 otherwise.

set -euo pipefail

SRC=${1:?usage: run_engine_spike.sh <meterless-checkout> [log-dir]}
LOG_DIR=${2:-"$PWD/engine-spike-logs"}
NODE_IMAGE=${NODE_IMAGE:-node:22-bookworm-slim}

SRC=$(cd "$SRC" && pwd)
mkdir -p "$LOG_DIR"
LOG_DIR=$(cd "$LOG_DIR" && pwd)
SUMMARY="$LOG_DIR/summary.txt"

for engine in hmem world-model; do
  [ -f "$SRC/engines/$engine/reference/package-lock.json" ] || {
    echo "missing $SRC/engines/$engine/reference/package-lock.json" >&2
    exit 2
  }
done

docker pull --quiet "$NODE_IMAGE" >/dev/null
{
  echo "ENG-013 engine spike"
  echo "date_utc:        $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "meterless_sha:   $(git -C "$SRC" rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "node_image:      $NODE_IMAGE"
  echo "image_digest:    $(docker image inspect --format '{{index .RepoDigests 0}}' "$NODE_IMAGE")"
  echo
} >"$SUMMARY"

failures=0

# One step = one fresh container, the engine folder mounted read-write so
# npm ci can create node_modules next to the reference.
run_step() {
  local engine=$1 name=$2 cmd=$3 status=0
  docker run --rm \
    --user "$(id -u):$(id -g)" -e HOME=/tmp -e CI=1 \
    -v "$SRC/engines/$engine:/engine" -w /engine/reference \
    "$NODE_IMAGE" bash -c "set -e; $cmd" >"$LOG_DIR/$name.log" 2>&1 || status=$?
  printf '%-34s exit %s\n' "$name" "$status" >>"$SUMMARY"
  [ "$status" -eq 0 ] || failures=$((failures + 1))
}

run_step hmem        hmem-install          "node --version; npm --version; npm ci --no-audit --no-fund"
run_step hmem        hmem-reference-tests  "npm test"
run_step hmem        hmem-conformance      "npx tsx ../conformance/runner.ts"

run_step world-model wm-install            "npm ci --no-audit --no-fund"
run_step world-model wm-reference-tests    "npm test"
run_step world-model wm-idempotency-check  "npx tsx scripts/idempotency-check.ts"
run_step world-model wm-conformance        "npx tsx ../conformance/runner.ts"

{
  echo
  for log in hmem-conformance wm-conformance; do
    echo "$log: $(grep -E 'checks passed' "$LOG_DIR/$log.log" | tail -1 | xargs)"
  done
  echo "failed_steps:    $failures"
} >>"$SUMMARY"

cat "$SUMMARY"
[ "$failures" -eq 0 ]
