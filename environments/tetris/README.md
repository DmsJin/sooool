# Tetris: single-player placement under response delay

A small deterministic Tetris engine written for this repository, with the classic one-piece preview. SOL sees the
game screen and names where the piece in play should go; a fixed key script carries the placement out. The piece
keeps falling while the answer is in flight, so at higher levels a late answer lands on the wrong piece or arrives
after the piece has locked.

## Engine

`engine.py` runs at 60 logic frames per second: 10×20 visible cells plus two hidden spawn rows, 7-bag randomiser,
SRS rotation with kicks, DAS/ARR on held left/right, 30-frame lock delay with 15 resets, guideline scoring and the
guideline gravity curve. Level = start level + lines/10. Everything is seeded; identical seeds and actions reproduce
identical games (`tests/test_tetris.py`). Hold exists in the engine but the policy does not use it.

## Observation (actor side)

`render.py` draws the complete public screen: the board including the two dark spawn rows, the piece in play, its
ghost landing outline, HOLD, one NEXT piece, SCORE/LINES/LEVEL. Nothing else is drawn: no column numbers, no row
numbers, no annotations. The runner upscales the 300×436 frame 2× (nearest neighbour) before sending it. The request
text (`task.py`) adds the policy, the measured delay statement for the run's mode and slowdown, and the actor's own
executed-placement history (last four lines). The actor never receives the board array, the bag, gravity timers or
the sampled delay.

## Action and executor (declared)

The actor returns one JSON placement for the piece in play: `{"piece": "S", "rot": 1, "col": 3, "reason": "..."}`.
`executor.py` converts it into keys using only the answer and the published spawn rule: rotate clockwise `rot`
times (three turns are one counter-clockwise press), move left/right until the piece's left edge is at `col`, hard
drop; press and release frames alternate so edge-triggered keys register. The executor never reads the piece
position or the board, so the same script works on a real screen.

Spawn detection is public: the executor counts a new piece when the NEXT box pixels change, when the spawn rows go
from empty to occupied, or when it pressed hard drop itself. Plans are indexed by that public piece count. An answer
that arrives after its piece locked is discarded (`stale`); an unparseable answer is discarded and a fresh screenshot
is sent (`invalid`). Both are counted in every summary.

## Request protocol

One request in flight. A screenshot is captured whenever the piece in play has no applied answer. In `simulate` the
answer is delivered after a delay sampled from the recipe's measured profile (the actor's computation pauses the
virtual clock); in `eval` it is delivered when it actually arrives on a continuously advancing wall clock. A game
slowdown factor (`args.slowdown`, 2 in the selected recipe) runs the game at 60/slowdown frames per wall second;
a measured wall delay therefore covers fewer game frames. The slowdown is a declared environment condition, like
Asterix's 5× and Badminton's 3×.

## Providers

- `claude` (default here): stateless Claude Code CLI calls (`claude_cli.py`); one fresh process per request, no
  tools, no session, no skills. Model and effort come from the recipe's `claude` block.
- `subscription`: the repository's ChatGPT/Codex transport (`runtime/subscription.py`), unchanged.
- `rules` (simulate only): the El-Tetris linear heuristic reading the TRUE board. It is an evaluator-side
  comparison under identical delay/executor settings, never an actor input.

## Evaluation and replay

Episodes start from deterministic mid-game states: `prefix` pieces placed by the rules baseline at zero delay from
a seeded game at the given start level. Summaries report lines cleared, new holes, stack-height change, pieces,
survival, calls, stale/invalid answers and capture-to-apply delay in game seconds. `sol replay tetris RUN` rebuilds
each episode from its recorded answers and apply frames without any model, checks every captured screenshot hash
and the final board. Hole and height metrics read the true board only after the fact.

## Limitations

- The engine is ours; it is not an emulated commercial Tetris. Classic-preview rules and SRS are documented above.
- With a one-piece preview every placement depends on the previous one, so a serial request cannot be pipelined
  further than the natural fall time; at normal speed and ~6 s response delay, levels ≥ 5 fail for the rules
  baseline as well (see `docs/tetris-autoresearch.md`).
- The `claude` transport reports token counts and CLI timing; hidden reasoning is not archived.
