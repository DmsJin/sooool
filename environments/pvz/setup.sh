#!/usr/bin/env bash
set -euo pipefail
source_dir="$1"
venv_dir="$2"
cmake -S "$source_dir" -B "$venv_dir/build" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DPVZ_DEBUG=OFF -DDO_FIX_BUGS=OFF
cmake --build "$venv_dir/build" --parallel 12
uv pip install --python "$venv_dir/bin/python" --editable "$source_dir[test]"
"$venv_dir/bin/python" -c 'import pvz_gym'
