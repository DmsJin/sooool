#!/bin/sh
set -eu
base=/home/ubuntu/wzh/touhou-sol-study/visual-policy-v3-20261016
while kill -0 2956123 2>/dev/null; do sleep 2; done
test -f "$base/comparison-v1/results.json"
cp "$base/policies.py" "$base/src/research/policies.py"
tar xzf "$base/kaguya-policy-v3-instant.tar.gz" -C "$base"
cd "$base/src"
export LD_LIBRARY_PATH=/home/ubuntu/wzh/touhou-sol-study/runtime/libs/usr/lib/x86_64-linux-gnu
exec /home/ubuntu/wzh/touhou-sol-study/.venv/bin/python -u -m research.visual_devset compare --dataset "$base/public-instant-v2" --output "$base/comparison-instant-v2" --suite /home/ubuntu/lzj/coding-agent-suite --candidates tracking_dodge_safe_intercept_v2 tracking_dodge_visual_v3 tracking_dodge_corridor_v3 --repeats 2 --workers 12 --limit 8 --envelope aggressive
