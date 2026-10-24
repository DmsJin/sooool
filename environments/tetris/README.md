# Tetris: single-player placement under response delay

A small deterministic Tetris engine written for this repository, with the classic one-piece preview. SOL sees the
game screen at fixed observation ticks and names where the falling piece should go; a fixed key script carries the
placement out. The piece keeps falling while the answer is in flight, so at higher levels a late answer arrives
after the piece has locked and is discarded.

## Engine

`engine.py` runs at 60 logic frames per second: 10×20 visible cells plus two hidden spawn rows, 7-bag randomiser,
SRS rotation with kicks, DAS/ARR on held left/right, 30-frame lock delay with 15 resets, guideline scoring and the
guideline gravity curve. Level = start level + lines/10. Everything is seeded; identical seeds and actions reproduce
identical games (`tests/test_tetris.py`). Hold exists in the engine but the policy does not use it.

## Observation (actor side)

`render.py` draws the complete public screen: the board including the two dark spawn rows, the piece in play, its
ghost landing outline, HOLD, one NEXT piece, SCORE/LINES/LEVEL. Nothing else is drawn: no column numbers, no row
numbers, no annotations. The runner captures the screen every `observation_stride_frames` (60 = once per game
second in the selected recipe) into a 9-frame window and, as in Asterix, sends the window's oldest, middle and
newest frames with their frame numbers, upscaled 2× (nearest neighbour). The request text (`task.py`) is Asterix's
form: a prefix stating the protocol and the measured delay (mean/median/P95 of the profile in game seconds, "the
actual delay of your request is unknown"), the policy, the output instructions, then the current frame, the image
frames and the actor's own last eight applied placements with their ages in frames. The actor never receives the
board array, the bag, gravity timers or the sampled delay.

## Action and executor (declared)

The actor returns one JSON placement for the piece in play: `{"rot": 1, "col": 3, "reason": "..."}`.
`executor.py` identifies the falling piece from its colour in the spawn rows (public pixels) when it appears and
converts the answer into keys using only that letter, the answer and the published spawn rule: rotate clockwise
`rot` times (three turns are one counter-clockwise press), move left/right until the piece's left edge is at `col`,
hard drop; press and release frames alternate so edge-triggered keys register. The executor never reads the piece
position or the board, so the same script works on a real screen.

Spawn detection is public too: the executor counts a new piece when the NEXT box pixels change, when the spawn rows
go from empty to occupied, or when it pressed hard drop itself. An answer that arrives after its piece locked is
discarded (`stale`), the placement analogue of Asterix discarding older replies; an unparseable answer is
discarded (`invalid`). Both are counted in every summary.

## Request protocol

Asterix's loop. One request in flight. A new request is captured at the first observation tick after the previous
reply arrived and its keys were pressed; ticks while a request is in flight (or keys are still being pressed) are
counted as `drops`. In `simulate` the answer is delivered after a delay sampled from the recipe's measured profile
(the actor's computation pauses the virtual clock); in `eval` it is delivered when it actually arrives on a
continuously advancing wall clock. A game slowdown factor (`args.slowdown`, 2 in the selected recipe) runs the game
at 60/slowdown frames per wall second; a measured wall delay therefore covers fewer game frames. The slowdown is a
declared environment condition, like Asterix's 5× and Badminton's 3×.

## Providers

- `claude` (default here): stateless Claude Code CLI calls (`claude_cli.py`); one fresh process per request, no
  tools, no session, no skills. Model and effort come from the recipe's `claude` block.
- `subscription`: the repository's ChatGPT/Codex transport (`runtime/subscription.py`), unchanged.
- `rules` (simulate only): the El-Tetris linear heuristic reading the TRUE board. It is an evaluator-side
  comparison under identical delay/executor settings, never an actor input.

## Evaluation and replay

Episodes start from deterministic mid-game states: `prefix` pieces placed by the rules baseline at zero delay from
a seeded game at the given start level (`--prefix 0` starts from an empty board). Summaries report lines cleared,
new holes, stack-height change, pieces, survival, calls, drops, stale/invalid answers and capture-to-apply delay in
game seconds (`issued.jsonl`, `decisions.jsonl`, `deliveries.json`, `actions.json`, `steps.jsonl`, `progress.json`
as in Asterix). `sol replay tetris RUN` rebuilds each episode from its recorded answers and delivery frames
without any model and checks every issued screenshot hash and the final board. Hole and height metrics read the
true board only after the fact.

## Limitations

- The engine is ours; it is not an emulated commercial Tetris. Classic-preview rules and SRS are documented above.
- With a one-piece preview every placement depends on the previous one, so a serial request cannot be pipelined
  further than the natural fall time; at normal speed and ~6 s response delay, levels ≥ 5 fail for the rules
  baseline as well (see `docs/tetris-autoresearch.md`).
- The `claude` transport reports token counts and CLI timing; hidden reasoning is not archived.
- Retained differences from Asterix: screenshots are 2× upscaled instead of 224×224 (cells must stay legible), the
  action is a placement executed as a key script instead of a held direction, episodes start from rules-placed
  mid-game states instead of reset noops, the delay statement is given in game time (profile seconds divided by the
  slowdown) rather than wall time, and development fixed cases were scored by "fewest new holes" instead of human
  annotations.
- Spawn detection can misidentify a piece that locks while part of it is still inside the spawn rows (a stack within
  two rows of the top); the game is effectively lost at that point.
