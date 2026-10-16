# Track the research, not just the best video

An evaluation record connects a hypothesis to a frozen configuration, model outputs, actual actions, and a decision. SOL generates prompt revisions and analyzes failures; humans supply preferences, inspect videos, and choose research constraints. The selected Asterix policy came from this human-guided autoresearch loop. Model weights are unchanged.

## Three different kinds of evidence

| Mode | What advances the game | What it proves |
|---|---|---|
| Profile simulation | A virtual clock with sampled historical response delays; computation may pause the environment | Closed-loop development under a specified delay model |
| Real-time subscription evaluation | A continuous wall clock, including actual model computation | Measured behavior with this subscription transport |
| Saved-action replay | Previously recorded actions; no model calls | Environment, screenshot and score integrity |

Fixed-screenshot preference tests measure agreement with annotated acceptable actions. They belong to development, and cannot establish game survival. Two observations from one event are correlated. A new response on an old screenshot is not an unseen-state test.

## Run and record

```bash
uv run sol simulate asterix --output runs/asterix-candidate-01
uv run sol record runs/asterix-candidate-01 --decision diagnostic \
  --note "Single development seed; inspect missed current-row pickups."

uv run sol eval asterix --output runs/asterix-realtime-01
uv run sol record runs/asterix-realtime-01 --decision retain \
  --note "Actual wall-clock trial completed; review score and lag before promotion."
```

Each directory contains `manifest.json` with the recipe and source hashes, `source_snapshot/`, the complete `task.txt`, issued requests and model public outputs, delivered actions, frame rewards/lives, `summary.json`, and `evaluation-record.json`. `assessments.jsonl` appends researcher decisions without replacing prior entries. Failures create `failure.json`; partial episodes stay interrupted and never become successful scores.

For each candidate, record:

1. **Hypothesis:** the concrete failure and expected behavior. Link a capture frame or video time.
2. **Change:** a prompt diff, output-format change, observation change, or scheduling change. Change one factor where practical.
3. **Conditions:** model/effort, prompt and system hashes, environment/source version, timing profile, seed, horizon, request capacity, and action-holding semantics.
4. **Evidence:** all attempted episodes, score, lives, elapsed game time, errors, observed latency and request drops. Compare at matching horizons; never extrapolate a short clip to a full game.
5. **Decision:** retain, reject, or diagnostic; explain the gate and remaining uncertainty. Freeze the candidate before confirmation and use fresh replies and additional seeds.

The agent may copy a recipe, edit its referenced prompt files, run the commands, inspect records, and append its conclusion. Do not change annotations to reward the candidate, pass evaluator truth or future delay draws to the actor, or delete losing runs to make a trend look better.

## Selected Asterix campaign

See [the research walkthrough](asterix-autoresearch.md), [machine-readable milestones](../research/asterix/evaluation-history.jsonl), and [selected raw records](../artifacts/asterix/serial-selected/). The walkthrough focuses on the route to the released configuration. Historical snapshots remain linked at a fixed source commit.

## Inspect a replay

With FFmpeg available, render the public English summaries next to verified game frames:

```bash
uv run python scripts/render_asterix_decisions.py \
  runs/asterix-development/seed-5 runs/asterix-development/replay.mp4 --music
uv run python scripts/audit_asterix_timing.py runs/asterix-development/seed-5
```

The video script verifies recorded rewards/lives and action identity, then optionally adds original quiet music and brightens only the game panel. It makes no model calls. Realtime renders say realtime replay; sampled-profile renders say profile simulation replay. The timing audit applies to simulation; realtime uses its actual delivery log.
