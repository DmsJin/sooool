#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git submodule update --init -- vendor/latency-aware-agents
uv sync --locked --python 3.12
uv run sol env setup touhou
uv run playwright install-deps chromium
uv run sol doctor
