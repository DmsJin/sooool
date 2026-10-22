#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git submodule update --init -- vendor/latency-aware-agents
uv sync --locked --python 3.12
for game in asterix touhou rhythm; do
  uv run sol env setup "$game"
done
uvx --from playwright==1.58.0 playwright install-deps chromium
uv run sol doctor
