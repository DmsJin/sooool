# Tetris evidence

- `evaluations.jsonl`: append-only registry written by `sol record` (schema version 2). Six portable runs of
  2026-10-24 of the aligned loop (fixed one-second observation ticks, three images per request): the selected
  `v11-short` policy simulate/eval at 2× and eval at 1×, the rules baseline simulate at 2× and 1×, and the rejected
  `v12c-tradeoff` candidate eval at 2× (`claude-eval-2x-v12c`, decision `reject`).
- `records/<record_id>/`: the compact, replayable evidence of each registered run, as Asterix retains it:
  `manifest.json` (recipe, mode, provider, clock), run and per-episode `summary.json`, `issued.jsonl` (observation
  frame, target piece, image frames and SHA-256s, sampled delay), `decisions.jsonl` (the same rows with delivery
  frame, public answer, call timing and status), `deliveries.json`, `actions.json` (key scripts), `progress.json`,
  `task.txt`, `transport-worker/transport.json`, `assessments.jsonl`. Screenshots and per-frame steps are not
  retained; replay re-renders every issued frame and checks its hash:
  `uv run sol replay tetris artifacts/tetris/records/claude-eval-2x`.
- `development/assessments.jsonl`: the scratch-harness candidate decisions that preceded the portable runner
  (different clip states, assumed or constant delays, several transports). They are provenance for the policy
  lineage in [the research record](../../docs/tetris-autoresearch.md), not registered results.
- `../../assets/tetris/claude-eval-2x-level5.gif`: deterministic replay rendering of the level-5 episode of
  `claude-eval-2x` (selected policy, actual clock) beside the rules baseline's episode from `rules-sim-2x`
  (`scripts/tetris_render.py`); not a screen capture.

Absolute `run` paths in the records point at the original output directories on the machine that produced them,
as for the other games.
