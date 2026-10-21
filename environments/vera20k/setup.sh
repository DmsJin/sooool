#!/usr/bin/env bash
set -euo pipefail
source_dir="$1"
venv_dir="$2"
uv pip install --python "$venv_dir/bin/python" 'maturin>=1.9,<2' 'Pillow==12.1.1'
cd "$source_dir"
export VIRTUAL_ENV="$venv_dir"
export PATH="$venv_dir/bin:$PATH"
maturin develop --uv --release --locked --manifest-path python/Cargo.toml
