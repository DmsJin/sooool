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
uv run sol profile  tetris --episode runs/tetris-live/episode-00-s0-l1-p20 --output profiles/tetris/new.json
uv run sol record   runs/tetris-live --decision diagnostic --note "..."
```

`--provider subscription` selects the repository's ChatGPT/Codex transport (GPT-6.1-sol) for either command;
`--provider rules` exists only for `simulate`. `--seed/--level/--prefix/--duration/--slowdown` override one
episode or one condition without editing the recipe; [`recipes/tetris-1x.json`](../recipes/tetris-1x.json) is the
normal-speed comparison.

## Three kinds of evidence

| Command | Clock | Delay | Proves |
|---|---|---|---|
| `sol simulate tetris` | virtual, pauses while the actor computes | sampled from the recipe profile, seeded per episode | closed-loop development under a declared delay model |
| `sol eval tetris` | wall, 60/slowdown frames per second | actual response time of the selected transport | measured behaviour of this transport at this slowdown |
| `sol replay tetris RUN` | none | recorded delivery frames | issued screenshot hashes, executor and final board integrity; no model calls |

## What a run retains

`manifest.json` (recipe, mode, provider, clock), `source_snapshot/`, `task.txt`, and per episode:
`issued.jsonl` (observation frame, target piece index, image frames and SHA-256s, sampled delay),
`decisions.jsonl` (the same rows with delivery frame, public answer, call timing and status
`applied`/`stale`/`invalid`), `deliveries.json`, `calls/call-*/` (exact prompt, the three images, public answer and
transport timing), `actions.json` (key scripts issued), `steps.jsonl`, `progress.json`, `summary.json`. The
run-level `summary.json` aggregates lines, new holes, height change, pieces, survival, calls, drops, stale/invalid
counts and capture-to-apply medians;
`evaluation-record.json` follows the shared schema and `sol record` appends it to
[`artifacts/tetris/evaluations.jsonl`](../artifacts/tetris/evaluations.jsonl).

## Delay profile

[`profiles/tetris/claude-opus-low-serial-v0.json`](../profiles/tetris/claude-opus-low-serial-v0.json) holds 71
capture-to-apply wall seconds measured on a serial real-clock run of the same transport and policy lineage
(median 5.9 s, p10 4.6 s, p90 7.8 s). `sol profile tetris` re-measures strictly serially on retained inputs; new
profiles replace this one in a copied recipe. The task prefix states the profile mean, median and 95th percentile
in game seconds for the run's slowdown, says that the actual delay is unknown, and says whether the actor's
computation advances the game.

## Slowdown

At normal speed a piece at level 5 locks about 3.5 s after it spawns on a half-full board, below the ~6 s delay of
every transport we measured, so answers arrive for the wrong piece. The selected recipe therefore declares a 2×
slowdown (one game second takes two wall seconds), as Asterix declares 5× and Badminton 3×. It is a condition of
the result, not a hidden assist: the actor's text says so, and `tetris-1x.json` keeps the normal-speed comparison.
