# Tetris evidence

- `evaluations.jsonl`: append-only registry written by `sol record` (schema version 2). Six fresh portable runs
  of 2026-10-24: Claude Opus simulate/eval at 2× and 1×, rules baseline simulate at 2× and 1×.
- `runs/<record_id>/`: the compact, replayable evidence of each registered run: `manifest.json` (recipe, mode,
  provider, clock), run and per-episode `summary.json`, `requests.jsonl` (capture frame, target piece, screenshot
  SHA-256, sampled or actual delivery, public answer, status), `actions.json` (key scripts), `task-example.txt`,
  `transport-worker/transport.json`, `assessments.jsonl`. Screenshots and per-frame steps are not retained; replay
  re-renders every captured frame and checks its hash: `uv run sol replay tetris artifacts/tetris/runs/claude-eval-2x`.
- `development/assessments.jsonl`: the scratch-harness candidate decisions that preceded the portable runner
  (different clip states, assumed or constant delays, several transports). They are provenance for the policy
  lineage in [the research record](../../docs/tetris-autoresearch.md), not registered results.
- `../../assets/tetris/claude-eval-2x-episode-04.gif`: deterministic replay rendering of `claude-eval-2x/episode-04-s0-l5-p20`
  (start level 5, actual clock, 7 lines, no new holes); not a screen capture.

Absolute `run` paths in the records point at the original output directories on the machine that produced them,
as for the other games.
