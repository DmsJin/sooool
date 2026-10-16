#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
cat AGENTS.md
cat environments/rhythm/AGENTS.md environments/touhou/AGENTS.md
export SOL_CODEX_BIN="${SOL_CODEX_BIN:-codex}"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$PWD/.browsers}"
export SOL_QUOTA_STOP_PERCENT=80
python_bin="${SOL_PYTHON:-.venv/bin/python}"
"$python_bin" -m runtime.cli doctor --auth
mkdir -p runs
pids=()
for game in rhythm touhou asterix; do
  "$python_bin" -u -m runtime.cli simulate "$game" --output "runs/package-validation-$game" >"runs/package-validation-$game.log" 2>&1 &
  pids+=("$!")
done
status=0
for pid in "${pids[@]}"; do wait "$pid" || status=1; done
exit "$status"
