#!/usr/bin/env bash
# Run one prompt against the Hermes harness and print metrics.
# Each `docker compose run` is a fresh container (= inherently "after restart").
# Requires the gateway up for metrics: docker compose -f hermes/... up -d gateway
# Usage: run-hermes.sh LABEL "prompt"
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$DIR/hermes/docker-compose.yml"
LABEL="$1"; PROMPT="$2"; shift 2

docker compose -f "$COMPOSE" run --rm --no-TTY cli -z "$PROMPT" \
  > "/tmp/hereval_${LABEL}.out" 2>/dev/null || true

SID=$(docker compose -f "$COMPOSE" exec -T gateway hermes sessions list 2>/dev/null \
        | awk 'NR>2{print $NF; exit}')
docker compose -f "$COMPOSE" exec -T gateway hermes sessions export --session-id "$SID" - \
  2>/dev/null > "/tmp/hereval_${LABEL}.jsonl"

python3 "$DIR/runners/metrics.py" "/tmp/hereval_${LABEL}.jsonl" "$LABEL"
