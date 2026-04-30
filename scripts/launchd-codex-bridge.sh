#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p "$ROOT/logs"
{
  echo "[launchd-wrapper] $(date '+%Y-%m-%d %H:%M:%S') starting"
  echo "[launchd-wrapper] pwd=$(pwd)"
  echo "[launchd-wrapper] python=$("$ROOT/.venv/bin/python" -c 'import sys; print(sys.executable)')"
} >> "$ROOT/logs/launchd-wrapper.log" 2>&1

exec "$ROOT/.venv/bin/python" -u "$ROOT/main_codex.py"
