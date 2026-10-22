#!/usr/bin/env bash
set -euo pipefail
if [ "$#" -eq 0 ]; then
  echo "Usage: bash scripts/setup.sh GAME [GAME ...] | all"
  exit 2
fi
cd "$(dirname "$0")/.."
git submodule update --init -- vendor/latency-aware-agents
uv sync --locked --python 3.12
uv run sol env setup "$@"
