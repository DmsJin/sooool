# Tetris: run, evaluate, replay

Tetris is a local environment ([scope and contract](../environments/tetris/README.md)). SOL sees the plain game
screen at one-second observation ticks (three timestamped frames per request, as in Asterix) and answers one
placement for the falling piece; a declared key script executes it. The selected condition is
[`recipes/tetris.json`](../recipes/tetris.json): policy `v11-short`, one request in flight, measured Claude Opus
delay profile, 2× game slowdown, three 60-second mid-game episodes (seeds 0/1/2 at start levels 1/3/5).

```bash
uv run sol env setup tetris
uv run sol simulate tetris --provider rules   --output runs/tetris-rules      # true-board baseline, sampled delays
uv run sol simulate tetris --provider claude  --output runs/tetris-sim        # Claude Code CLI decisions, sampled delays
uv run sol eval     tetris --provider claude  --output runs/tetris-live       # actual wall clock and actual latency
uv run sol replay   tetris runs/tetris-live                                   # zero-model replay check
uv run sol record   runs/tetris-live --decision diagnostic --note "..."
```

`--provider subscription` selects the repository's ChatGPT/Codex transport (GPT-6.1-sol) for either command;
`--provider rules` exists only for `simulate`. `--seed/--level/--prefix/--duration/--slowdown` override one
episode or one condition without editing the recipe and are folded into the frozen manifest; a recipe the runner
cannot honour (slowdown below 1, a window smaller than the three images sent, more than one request in flight) is
rejected before any run directory exists; [`recipes/tetris-1x.json`](../recipes/tetris-1x.json) is the
normal-speed comparison.

## Three kinds of evidence

| Command | Clock | Delay | Proves |
|---|---|---|---|
| `sol simulate tetris` | virtual, pauses while the actor computes | sampled from the recipe profile, seeded per episode | closed-loop development under a declared delay model |
| `sol eval tetris` | wall, 60/slowdown frames per second | actual response time of the selected transport | measured behaviour of this transport at this slowdown |
| `sol replay tetris RUN` | none | recorded delivery frames | every issued image (frames and hashes), request targets, executor statuses, sampled-delay arithmetic, key scripts, drops, horizon and every summary number re-derived; no model calls |

## What a run retains

`manifest.json` (recipe with any CLI overrides folded in, mode, provider, clock), `source_snapshot/`, `task.txt`,
`provenance.json` (interpreter, Pillow, numpy, source commit), `transport-worker/transport.json` (adapter, CLI
version, resolved model ids), and per episode:
`issued.jsonl` (observation frame, target piece index, image frames and SHA-256s, sampled delay),
`decisions.jsonl` (the same rows with delivery frame, public answer, call timing and status
`applied`/`stale`/`invalid`), `deliveries.json`, `calls/call-*/` (exact prompt, the three images, public answer and
transport timing), `actions.json` (key scripts issued), `steps.jsonl`, `progress.json`, `summary.json`. The
run-level `summary.json` aggregates lines, new holes, height change, pieces, survival, calls, drops, stale/invalid
counts and capture-to-apply medians;
`evaluation-record.json` follows the shared schema and `sol record` appends it to
[`artifacts/tetris/evaluations.jsonl`](../artifacts/tetris/evaluations.jsonl).

## Delay profile

[`profiles/tetris/claude-opus-low-serial-v0.json`](../profiles/tetris/claude-opus-low-serial-v0.json) holds 68
capture-to-apply wall seconds measured on a serial real-clock run of the same transport and an earlier, longer
prompt of this policy lineage (median 5.9 s, p10 4.8 s, p90 7.4 s, p95 9.0 s). A new profile is the `call_wall_seconds` column of a serial
`sol eval tetris` run's `decisions.jsonl`, saved in the same JSON form and named in a copied recipe. The task prefix states the profile mean, median and 95th percentile
in game seconds for the run's slowdown, says that the actual delay is unknown, and says whether the actor's
computation advances the game.

## Slowdown

At normal speed a piece at level 5 locks about 3.5 s after it spawns on a half-full board, below the ~6 s delay of
every transport we measured, so answers arrive for the wrong piece. The selected recipe therefore declares a 2×
slowdown (one game second takes two wall seconds), as Asterix declares 5× and Badminton 3×. It is a condition of
the result, not a hidden assist: the actor's text says so, and `tetris-1x.json` keeps the normal-speed comparison.
