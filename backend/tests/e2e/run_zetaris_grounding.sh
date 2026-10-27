#!/usr/bin/env bash
# ENG-047 live Zetaris grounding check (operator host only).
#
# Read-only by construction: the live test issues SELECTs against the governed
# aew_pg views and never calls the publisher's apply path. The product database
# and the Zetaris instance must already be up, with the read model published
# (publisher --apply, then a green --check). See
# docs/evidence/zetaris-agent-proof-2026-10-27.md for the full runbook.
#
# Required environment (values come from the repo-root .env or the shell;
# the API key is used by the process, never echoed, never written to evidence):
#   ZETARIS_REST_URL          e.g. http://localhost:8888/api/v1.0
#   ZETARIS_ORG_ID            numeric organisation id
#   ZETARIS_API_KEY           bearer API token
#   ZETARIS_TEST_PROJECT_ID   project id that has an ACTIVE published binding
#
# Usage:
#   backend/tests/e2e/run_zetaris_grounding.sh [log-dir]
#
# Windows (PowerShell, no bash):
#   $env:ZETARIS_LIVE=1; $env:ZETARIS_GROUNDING_OUT="zetaris-grounding.json"
#   python -m pytest backend/tests/e2e/test_zetaris_grounding.py -v
#
# Exit 0 only when the deterministic chain and the live check both pass.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
LOG_DIR=${1:-$(mktemp -d -t zetaris-grounding-XXXXXX)}
mkdir -p "$LOG_DIR"
LOG_DIR=$(cd "$LOG_DIR" && pwd)

: "${ZETARIS_REST_URL:?set ZETARIS_REST_URL (e.g. http://localhost:8888/api/v1.0)}"
: "${ZETARIS_ORG_ID:?set ZETARIS_ORG_ID (numeric)}"
: "${ZETARIS_API_KEY:?set ZETARIS_API_KEY}"
: "${ZETARIS_TEST_PROJECT_ID:?set ZETARIS_TEST_PROJECT_ID}"

export ZETARIS_LIVE=1
export ZETARIS_GROUNDING_OUT="$LOG_DIR/zetaris-grounding.json"

cd "$ROOT/backend"

echo "== deterministic chain (mocked Zetaris, no network) =="
python -m pytest tests/e2e/test_zetaris_grounding.py -v \
  --deselect tests/e2e/test_zetaris_grounding.py::test_live_zetaris_grounds_a_real_project_record \
  | tee "$LOG_DIR/deterministic.log"

echo "== live read-only grounding against $ZETARIS_REST_URL (org $ZETARIS_ORG_ID) =="
python -m pytest tests/e2e/test_zetaris_grounding.py::test_live_zetaris_grounds_a_real_project_record -v \
  | tee "$LOG_DIR/live.log"

echo "sanitized evidence JSON: $ZETARIS_GROUNDING_OUT"
echo "logs: $LOG_DIR"
