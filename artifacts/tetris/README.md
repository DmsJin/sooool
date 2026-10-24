# Tetris evidence

- `evaluations.jsonl`: append-only registry written by `sol record` (schema version 2). Six portable runs of
  2026-10-24 of the aligned loop (fixed one-second observation ticks, three images per request): the selected
  `v11-short` policy simulate/eval at 2× and eval at 1×, the rules baseline simulate at 2× and 1×, and the rejected
  `v12c-tradeoff` candidate eval at 2× (`claude-eval-2x-v12c`, decision `reject`).
- `records/<record_id>/`: the compact, replayable evidence of each registered run: `manifest.json` (recipe,
  mode, provider, clock), `task.txt` (exact actor text), run and per-episode `summary.json`, per-episode
  `decisions.jsonl` (observation frame, target piece, image frames and SHA-256s, sampled or actual delivery frame,
  public answer, call timing, status), `assessments.jsonl`. Screenshots, key scripts and per-frame steps are not
  retained; replay re-renders every issued frame, recomputes the key scripts and checks hashes and the final
  board: `uv run sol replay tetris artifacts/tetris/records/claude-eval-2x`. `claude-eval-2x-v12c/prompt.diff` is
  the rejected candidate's only difference from the selected policy.
- `../../assets/tetris/claude-eval-2x-level5.gif`: deterministic replay rendering of the level-5 episode of
  `claude-eval-2x` (selected policy, actual clock) beside the rules baseline's episode from `rules-sim-2x`
  (`scripts/tetris_render.py`); not a screen capture.

Absolute `run` paths in the records point at the original output directories on the machine that produced them,
as for the other games.
