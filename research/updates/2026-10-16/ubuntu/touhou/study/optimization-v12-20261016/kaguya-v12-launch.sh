#!/bin/sh
set -eu
base=/home/ubuntu/wzh/touhou-sol-study/optimization-v12-20261016
tar xzf "$base/kaguya-v12-source.tar.gz" -C "$base/src"
python3 - <<'PY'
from pathlib import Path
import json,hashlib,urllib.request
b=Path('/home/ubuntu/wzh/touhou-sol-study/optimization-v12-20261016');p=json.loads((b/'protocol.json').read_text())
for name,h in p['source_sha256'].items():assert hashlib.sha256((b/'src/research'/name).read_bytes()).hexdigest()==h
assert hashlib.sha256(Path(p['base']['profile']).read_bytes()).hexdigest()==p['profile_sha256']
with urllib.request.urlopen('http://127.0.0.1:18791/engine.mjs',timeout=5) as r:assert hashlib.sha256(r.read()).hexdigest()==p['base']['engine_sha256']
print('preflight_source_profile_existing_http_engine_passed',flush=True)
PY
cd "$base/src"
export LD_LIBRARY_PATH=/home/ubuntu/wzh/touhou-sol-study/runtime/libs/usr/lib/x86_64-linux-gnu
exec /home/ubuntu/wzh/touhou-sol-study/.venv/bin/python -u -m research.batch --config "$base/protocol.json" --output "$base/episodes" --episode-workers 2
