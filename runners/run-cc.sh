#!/usr/bin/env bash
# Run one prompt against the clean Claude Code harness and print metrics.
# Usage: run-cc.sh LABEL "prompt" [extra claude args, e.g. --continue]
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="$1"; PROMPT="$2"; shift 2
OUT="/tmp/cceval_${LABEL}.jsonl"
docker compose -f "$DIR/clean-cc/docker-compose.yml" exec -T -w /workspace cc \
  claude -p "$PROMPT" --output-format stream-json --verbose \
  --dangerously-skip-permissions --strict-mcp-config "$@" > "$OUT"
python3 "$DIR/runners/metrics.py" "$OUT" "$LABEL"
