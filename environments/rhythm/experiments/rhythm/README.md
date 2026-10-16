# Screenshot-only rhythm autoresearch

Acceptance: native audio/browser at 1x, three consecutive complete 30-second episodes, weighted accuracy >=95% and zero missed notes. Empty presses are auxiliary diagnostics, not an added acceptance threshold.

Policy receives actual canvas PNG, exact rendered-frame audio time and public viewport geometry only. GPT identifies lane and note pixel center; the executor converts that GPT-provided coordinate to a timestamp using the public 1.8-second highway travel time. It performs no automatic note detection. Hidden chart/state is restricted to evaluator calibration, never sent to policy.

Paid target: gpt-6.1-sol, Ultrafast, low, direct Responses API. Profiling is strictly serial. Subscription computations use the original native ChatGPT app-server wrapper with forced subscription auth and no paid fallback. Subscription real compute time and sampled target response delay are separate. Target API request capacity and actual subscription worker count are also separate.

`runs/budget.json` is the sole process-safe USD30 cumulative ledger, including profiling, final verification, retries and uncertain in-flight charges. Credentials enter getpass/stdin and are never persisted. Runtime evidence is ignored by Git.

`profile.py`: serial paid workload calibration. `simulate.py`: preserved initial baseline. `simulate_candidate.py`: separately versioned imminent-action-guard candidate. `realtime.py`: frozen native-audio live API verification, with continuous browser clock, request deadline and exact action acknowledgements. `test_visual_env.py`: evaluator-only oracle/control interface validation; this is not evidence of GPT solving the task.

All candidate results must be complete before calculating a group mean. Interrupted episodes retain their evidence and retry relationship; completed episodes are not replaced. Simulated results never count as real-time API success.


## Completed native API campaign

See [RESULTS.md](RESULTS.md) for the verified three consecutive native 1x API episodes (52 PERFECT each), the complete failed experiments, costs and evidence paths. The selected pipeline is `cropped_profile.py` → `cropped_simulate.py` → `realtime_v2.py`; older modules are preserved experiment versions. `runs` points to durable local evidence outside the Git worktree, including the cumulative budget ledger.

Install research dependencies in an isolated virtual environment with `pip install -e '.[research]'` and install a Playwright Chromium browser. Start the static `dist` server on an available loopback port after reading applicable AGENTS.md instructions. Native verification additionally needs the same authorized 30-second preview audio file. The final remote machine required an explicit Chromium executable and an isolated library directory; those paths are captured in the frozen manifest.

The exact native command used was:

```sh
LD_LIBRARY_PATH=/tmp/dfjk-browser-libs/root/usr/lib/x86_64-linux-gnu \
/tmp/dfjk-browser-env/bin/python -m experiments.rhythm.realtime_v2 \
  --url http://127.0.0.1:18895 \
  --audio /tmp/dfjk-remote-browser/dfjk-preview.m4a \
  --browser-executable /home/ubuntu/.cache/ms-playwright/chromium_headless_shell-1248/chrome-headless-shell-linux64/chrome-headless-shell \
  --run final-remote-r1 --variant pixels_cropped_v1 \
  --capacity 20 --cadence .10 --episodes 3 \
  --commit-guard-ms 50 --request-deadline 1.75 --late-grace-ms 55 \
  --native-fps 0 --effort low --max-output 512 --video --record-final
```

Use a new run name for another execution. This command makes paid calls and reads the key through a hidden prompt; it does not put the key in the command or a file. The existing ledger retains the original $30 ceiling and unresolved reservations. Subscription simulations require the authorized native Codex workers on the original SSH host; they never substitute API credentials when subscription authentication is unavailable.
