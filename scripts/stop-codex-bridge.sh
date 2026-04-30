#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT/bridge.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "Bridge is not running"
  exit 0
fi

PID="$(cat "$PID_FILE" || true)"
if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "Stopped Lark Codex bridge with PID $PID"
else
  echo "Bridge PID $PID is not running"
fi
rm -f "$PID_FILE"

