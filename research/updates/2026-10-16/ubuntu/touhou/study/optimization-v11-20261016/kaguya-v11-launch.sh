#!/bin/sh
set -eu
base=/home/ubuntu/wzh/touhou-sol-study/optimization-v11-20261016
tar xzf "$base/kaguya-v11-source.tar.gz" -C "$base/src"
cd "$base/src"
export LD_LIBRARY_PATH=/home/ubuntu/wzh/touhou-sol-study/runtime/libs/usr/lib/x86_64-linux-gnu
exec /home/ubuntu/wzh/touhou-sol-study/.venv/bin/python -u -m research.visual_devset compare --dataset /home/ubuntu/wzh/touhou-sol-study/visual-policy-v3-20261016/public --output "$base/comparison" --suite /home/ubuntu/lzj/coding-agent-suite --candidates tracking_dodge_safe_intercept_v2 tracking_dodge_safe_intercept_medium_v11 tracking_dodge_mechanics_v10 tracking_dodge_mechanics_medium_v11 --repeats 2 --workers 12 --limit 26 --envelope aggressive --shuffle-seed 1129 --effort low --effort-by-candidate '{"tracking_dodge_safe_intercept_medium_v11":"medium","tracking_dodge_mechanics_medium_v11":"medium"}'
