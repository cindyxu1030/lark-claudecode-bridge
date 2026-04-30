#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PID_FILE="$ROOT/bridge.pid"
if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "${OLD_PID:-}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Bridge already running with PID $OLD_PID"
    exit 0
  fi
fi

mkdir -p logs
nohup "$ROOT/.venv/bin/python" -u "$ROOT/main_codex.py" > "$ROOT/logs/stdout.log" 2> "$ROOT/logs/stderr.log" &
echo "$!" > "$PID_FILE"
echo "Started Lark Codex bridge with PID $(cat "$PID_FILE")"
