#!/usr/bin/env bash
# ENG-018 live engine check: the real H-MEM sidecar across two backend sessions
# and a sidecar restart, then the fail-closed path.
#
# Usage:
#   backend/tests/integration/run_meterless_engine.sh [log-dir]
#   NIGHTSHIFT_LIVE=1 backend/tests/integration/run_meterless_engine.sh [log-dir]
#
# 1. builds services/hmem; the official conformance suite runs inside the
#    build against the vendored module the sidecar serves;
# 2. starts the sidecar on a fresh data volume and a private network;
# 3. runs tests/integration/test_meterless_engine.py once per phase, each in a
#    fresh backend container: session_1, then a sidecar restart, session_2,
#    then the sidecar is stopped and phase down runs;
# 4. writes the logs, the store's ledger and a summary to <log-dir>.
#
# Sponsor code runs only in the sidecar container. With NIGHTSHIFT_LIVE=1 the
# architecture call goes to Nightshift (repo-root .env); otherwise the model is
# scripted and the engine is still real. Exit 0 when every step passed.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
LOG_DIR=${1:-$(mktemp -d -t meterless-engine-XXXXXX)}
PYDEPS=${PYDEPS_DIR:-"$HOME/.cache/aew-backend-pydeps"}
IMAGE=${HMEM_IMAGE:-aew-hmem:dev}
NAME=aew-hmem-it
PROJECT=${HMEM_TEST_PROJECT_ID:-$(python3 -c 'import uuid; print(uuid.uuid4())')}
mkdir -p "$LOG_DIR" "$PYDEPS"
LOG_DIR=$(cd "$LOG_DIR" && pwd)
SUMMARY="$LOG_DIR/summary.txt"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  docker volume rm "$NAME-data" >/dev/null 2>&1 || true
  docker network rm "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT
cleanup

docker build -t "$IMAGE" "$ROOT/services/hmem" >"$LOG_DIR/build.log" 2>&1
docker run --rm --entrypoint cat "$IMAGE" /srv/hmem/conformance.log >"$LOG_DIR/conformance.log"
docker network create "$NAME" >/dev/null
docker run -d --name "$NAME" --network "$NAME" -v "$NAME-data:/data" "$IMAGE" >/dev/null

wait_healthy() {
  for _ in $(seq 1 50); do
    docker exec "$NAME" node -e "fetch('http://127.0.0.1:8099/healthz').then(r => process.exit(r.ok ? 0 : 1), () => process.exit(1))" \
      >/dev/null 2>&1 && return 0
    sleep 0.2
  done
  echo "hmem-service did not become healthy" >&2
  return 1
}

{
  echo "ENG-018 live engine check"
  echo "date_utc:        $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_head:        $(git -C "$ROOT" rev-parse --short HEAD) (+ working tree)"
  echo "image:           $IMAGE $(docker image inspect --format '{{.Id}}' "$IMAGE" | cut -c1-19)"
  echo "project_id:      $PROJECT"
  echo "model:           $([ "${NIGHTSHIFT_LIVE:-}" = 1 ] && echo 'Nightshift (live)' || echo 'scripted (engine real)')"
  echo "conformance:     $(grep -E 'checks passed' "$LOG_DIR/conformance.log" | xargs)"
  echo
} >"$SUMMARY"

failures=0
run_phase() {
  local phase=$1 status=0 mount workdir live_env=()
  if [ "${NIGHTSHIFT_LIVE:-}" = 1 ]; then
    mount=(-v "$ROOT:/repo:ro"); workdir=/repo/backend; live_env=(-e NIGHTSHIFT_LIVE=1)
  else
    mount=(-v "$ROOT/backend:/repo/backend:ro"); workdir=/repo/backend
  fi
  docker run --rm --network "$NAME" --user "$(id -u):$(id -g)" \
    -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONUSERBASE=/deps \
    -e HMEM_LIVE=1 -e HMEM_PHASE="$phase" -e HMEM_BASE_URL="http://$NAME:8099" -e HMEM_TEST_PROJECT_ID="$PROJECT" \
    "${live_env[@]}" -v "$PYDEPS:/deps" "${mount[@]}" -w "$workdir" python:3.12-slim bash -c \
    "pip install -q --user --no-warn-script-location -r requirements.txt && python -m pytest -p no:cacheprovider \
       -o addopts='' -q -rA -s -o log_cli=true --log-cli-level=INFO tests/integration/test_meterless_engine.py" \
    >"$LOG_DIR/$phase.log" 2>&1 || status=$?
  printf '%-16s exit %s  %s\n' "$phase" "$status" "$(grep -E '[0-9]+ (passed|failed)' "$LOG_DIR/$phase.log" | tail -1)" >>"$SUMMARY"
  [ "$status" -eq 0 ] && grep -qE '1 passed' "$LOG_DIR/$phase.log" || failures=$((failures + 1))
}

wait_healthy
run_phase session_1
docker restart "$NAME" >/dev/null && wait_healthy
echo "sidecar restarted between sessions" >>"$SUMMARY"
run_phase session_2
docker exec "$NAME" cat "/data/$PROJECT/ledger.jsonl" >"$LOG_DIR/ledger.jsonl"
docker exec "$NAME" cat "/data/$PROJECT/state.json" >"$LOG_DIR/state.json"
docker logs "$NAME" >"$LOG_DIR/sidecar.log" 2>&1
docker stop "$NAME" >/dev/null
echo "sidecar stopped" >>"$SUMMARY"
run_phase down

{
  echo
  echo "recall log lines:"
  grep -hE '^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*(H-MEM recalled|no H-MEM lesson)' "$LOG_DIR/session_2.log" | sed 's/^/  /' || true
  echo "ledger actions:  $(python3 -I -c 'import json,sys; print([json.loads(l)["action"] for l in open(sys.argv[1])])' "$LOG_DIR/ledger.jsonl")"
  echo "failed_steps:    $failures"
} >>"$SUMMARY"

cat "$SUMMARY"
echo "logs: $LOG_DIR"
[ "$failures" -eq 0 ]
