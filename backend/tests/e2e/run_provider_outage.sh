#!/usr/bin/env bash
# ENG-052 live sponsor outage and recovery check (operator host only).
#
# Drives the gated test in test_provider_outage.py through a real stop/start
# cycle of one local sponsor container and writes sanitized phase evidence.
# The test is read-only with respect to product data; only the sponsor
# container lifecycle is touched, and a trap restarts it on any failure.
#
# Defaults target the Zetaris compose stack recorded in
# docs/evidence/zetaris-stack-2026-10-23.md. Override for another container:
#   SPONSOR_NAME=meterless_engine SPONSOR_CONTAINER=aew-hmem-it \
#     backend/tests/e2e/run_provider_outage.sh [log-dir]
#
# Nightshift is a desktop runtime on a separate machine and cannot be stopped
# from here: run its outage phase manually (quit the runtime, execute the down
# invocation below with SPONSOR_NAME=nightshift, restart it, run the up phase).
#
# Required environment for the health service's default client:
#   ZETARIS_REST_URL, ZETARIS_ORG_ID, ZETARIS_API_KEY
# The API key is used by the process and swept from evidence; never echoed.
#
# Usage:
#   backend/tests/e2e/run_provider_outage.sh [log-dir]      # bash/Git Bash/WSL
#
# PowerShell cannot execute .sh directly (it returns silently or opens an
# association); use "bash backend/tests/e2e/run_provider_outage.sh <log-dir>"
# with Git Bash/WSL, or follow the per-phase PowerShell commands in
# docs/evidence/provider-failure-2026-10-27.md section 5.
#
# Exit 0 only when the up-baseline, down and recovered-up phases all pass.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
LOG_DIR=${1:-$(mktemp -d -t provider-outage-XXXXXX)}
mkdir -p "$LOG_DIR"
LOG_DIR=$(cd "$LOG_DIR" && pwd)

SPONSOR_NAME=${SPONSOR_NAME:-zetaris}
SPONSOR_CONTAINER=${SPONSOR_CONTAINER:-zetaris-api-1}

: "${ZETARIS_REST_URL:?set ZETARIS_REST_URL (e.g. http://localhost:8888/api/v1.0)}"
: "${ZETARIS_ORG_ID:?set ZETARIS_ORG_ID (numeric)}"
: "${ZETARIS_API_KEY:?set ZETARIS_API_KEY}"

cd "$ROOT/backend"
export SPONSOR_LIVE=1

run_phase() {
    local phase="$1"
    export SPONSOR_PHASE="$phase"
    export SPONSOR_NAME
    export SPONSOR_OUTAGE_OUT="$LOG_DIR/${SPONSOR_NAME}-${phase}.json"
    echo "== phase $phase ($SPONSOR_NAME) =="
    python -m pytest tests/e2e/test_provider_outage.py::test_live_sponsor_outage_and_recovery_phases -v \
        | tee "$LOG_DIR/${SPONSOR_NAME}-${phase}.log"
}

restart_sponsor() {
    echo "restoring sponsor container $SPONSOR_CONTAINER"
    docker start "$SPONSOR_CONTAINER" >/dev/null 2>&1 || true
}
trap restart_sponsor EXIT

# 1. healthy baseline proves the sponsor really was up before the outage.
run_phase up

# 2. controlled outage: the health endpoint must honestly report it, never
#    claim verified, and the test's secret sweep must still pass.
docker stop "$SPONSOR_CONTAINER" >/dev/null
run_phase down

# 3. restoration: a fresh verified check with new provenance, last-success
#    continuity having been exercised deterministically in the sandbox suite.
docker start "$SPONSOR_CONTAINER" >/dev/null
trap - EXIT
run_phase up

echo "sanitized evidence JSON and logs: $LOG_DIR"
