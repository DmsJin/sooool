# Tetris evidence

- `evaluations.jsonl`: the append-only registry written by `sol record` (shared schema version 2), one row per
  run with the run and per-episode summaries and the researcher decision: the selected `v11-short` policy on the
  actual clock at 2× (`claude-eval-2x`, retain), its simulation at 2× and evaluation at 1×, the rules baseline
  simulations at 2× and 1×, and the rejected `v12c-tradeoff` candidate on the actual clock at 2×
  (`claude-eval-2x-v12c`, reject). [The research record](../../docs/tetris-autoresearch.md) reads these rows.
- `records/claude-eval-2x/`: the selected run's replayable evidence: `manifest.json`, `task.txt` (exact actor
  text), run and per-episode `summary.json`, per-episode `decisions.jsonl` (observation frame, target piece, image
  frames and SHA-256s, delivery frame, public answer, call timing, status). No screenshots are retained; replay
  re-renders every issued frame, recomputes the key scripts and checks hashes and the final board:
  `uv run sol replay tetris artifacts/tetris/records/claude-eval-2x` (also `tests/test_tetris.py`).
- `v12c-prompt.diff`: the rejected candidate's only difference from the selected policy.
- `../../assets/tetris/claude-eval-2x-level5.gif`: deterministic replay rendering of the selected run's level-5
  episode beside the rules baseline's (`scripts/tetris_render.py`); not a screen capture.

Absolute `run` paths in the records point at the original output directories on the machine that produced them,
as for the other games.
