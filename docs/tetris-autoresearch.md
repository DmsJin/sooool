# SOL researches a visual Tetris policy

The working object is one placement per piece, read from the plain game screen at fixed observation ticks and
executed by a key script that never looks at the board ([environment contract](../environments/tetris/README.md),
[run and record](tetris.md)). The research question was the same as for the other games: can a frozen visual model
keep a real-time game under control while its own answers are late. Development numbers below come from a scratch
harness that preceded the portable runner (constant or assumed delays, other clip states); the registered numbers
are the fresh portable runs in [`artifacts/tetris/evaluations.jsonl`](../artifacts/tetris/evaluations.jsonl).

## 1. How the selected policy was reached

**Measure the delay before trusting a score.** The first protocol asked for six placements per screenshot and
assumed a 1.5 s delay, under which Haiku appeared to beat the rules baseline. A strictly serial measurement of the
same request took 40–46 s; the result was discarded and every later comparison uses a measured profile. Serial
wall delays of one placement per request from the plain screen:

| Transport | Serial wall delay | Fixed-set accuracy (43 states) |
|---|---:|---:|
| Claude Sonnet, low / medium effort | 8.5 / 11.1 s | 57% / 62% |
| Claude Opus, low effort (selected) | 6.5 s | 78% |
| Claude Fable 5.1, low / medium / high effort | 4.7 / 16.1 / 18.8 s | 46% / 63% / 75% |
| GPT-6.1-sol via `runtime/subscription.py`, priority tier | ~6 s (3–8 s) | 98% |

Accuracy counts an answer as acceptable when it is one of the placements with the fewest new holes on that board.
The ChatGPT subscription cannot open the ultrafast tier, so the ~1.5 s delays of the paid Asterix/Rhythm runs are
not available on a subscription; GPT runs were stopped after these measurements and the Claude transport is the
selected condition.

**Honest screen and executor.** Early candidates annotated the screenshot with column numbers and executed
placements with a controller that read the piece position from the engine. Both were withdrawn: the actor reads the
raw screen, and the executor presses keys computed from the answer and the piece letter read from the public spawn
rows. The rules baseline reaches identical placements through the same key scripts (`tests/test_tetris.py`).

**One rule and one table.** On a 60-state set of closed-loop failures, hole mistakes had two causes: knowingly
accepting a gap when a gap-free spot existed (28/48) and misjudging a fit by one row (16/48). A gap-free-first rule
plus a table of the column-height patterns each rotation fits raised acceptable answers from 103/180 to 128/180
and shortened the output; model-authored memory, same-screenshot voting and rewritten fit rules did not move the
held-out set and were dropped. Closed-loop, the policy then matched the true-board baseline (5.7 vs 6.5 lines per
30 s clip, same holes) under a constant delay, and failed the same way as the baseline at normal speed on the
actual clock (levels ≥ 3: the piece locks before the ~6 s answer arrives). A declared 2× slowdown restored control;
3× added nothing.

**Aligned with Asterix's loop.** The portable version then took Asterix's observation protocol as is: fixed
60-frame observation ticks into a 9-tick window, the window's oldest/middle/newest frames with frame numbers, the
actor's applied placements with ages, Asterix's system text verbatim and its task-prefix form (profile
mean/median/P95 in game time, "the actual delay of your request is unknown", mode sentence swap); no labels on the
screen, no piece letter in the answer, a one-line game description instead of a page, and a corrected definition
of a hole. That is `v11-short`. Single episodes were run after each change until the scheme was fixed.

## 2. Two decisions the model gets wrong, on fixed screenshots

Watching `v11-short`'s full game (seed 0, level 1, from an empty board) showed two recurring misplacements.
Both were cut out as fixed cases (the exact request text and three images of that moment) and re-asked five times
per prompt variant; scoring is new holes and rows completed by the answered placement on the true board.

| Case | True heights | Rules baseline | `v11-short` | `v12c-tradeoff` |
|---|---|---|---|---|
| 15: O, stack 1-3-4-7-7-8-8-8-7-8 | misread the 3/4 step | O on 0-1 (one hole) | 5/5 gap-free on 3-4 | 4/5 (one misread) |
| 28: J, well in column 3 beside 5-high stack | fill the well | vertical J in the well: one hole, two rows | 1/5 fill the well, 4/5 play safe | 4/5 fill, 1/5 safe |

Case 15 is a reading error: about one answer in five mis-counts a column height by one, with every prompt, and the
answer is then internally consistent with the wrong reading. No prompt changes this; only repeated reads (voting)
or a stronger reader would. Case 28 is a rule the prompt imposed: `v11-short`'s "accept a gap only when no gap-free
spot exists" forbids the well fill that completes two rows. `v12c-tradeoff` adds the one exception (two or more
completed rows are worth one hole; check the deepest well first; do not hold a well open beside a five-high stack)
and fixes the decision four times in five without hurting case 15 (two intermediate wordings did not and were
dropped).

## 3. Fresh portable validation (three episodes)

Both prompts were then run on the recipe's three 60-second episodes (seeds 0/1/2 at start levels 1/3/5, 20
rules-placed pieces before the clip) with the actual clock at the declared 2× slowdown, serially, plus the
simulation, the true-board baseline and the normal-speed comparison. Means over three episodes; "avoidable" counts
applied decisions that created a hole where the rules baseline had a gap-free placement for the same piece.

| Run | Policy | Provider | Clock | Slowdown | Lines | New holes | Alive | Stale | Avoidable | Capture→apply (game s) |
|---|---|---|---|---|---:|---:|---|---:|---:|---:|
| `claude-eval-2x` **(selected)** | `v11-short` | Claude Opus low, stateless CLI | wall | 2× | 5.67 | 0.33 | 3/3 | 0 | 1/55 | 2.85 (wall median 5.3 s) |
| `claude-eval-2x-v12c` (rejected) | `v12c-tradeoff` | Claude Opus low | wall | 2× | 3.67 | 5.33 | 3/3 | 3 | 0/45 | 3.12 (wall median 6.2 s) |
| `claude-sim-2x` | `v11-short` | Claude Opus low | virtual, sampled profile | 2× | 3.67 | 8.67 | 2/3 | 3 | — | 2.77 |
| `rules-sim-2x` | — | rules baseline (true board) | virtual, sampled profile | 2× | 5.67 | 1.67 | 3/3 | 0 | — | 2.77 |
| `claude-eval-1x` | `v11-short` | Claude Opus low | wall | 1× | 1.67 | 5.67 | 2/3 | 5 | — | 6.26 |
| `rules-sim-1x` | — | rules baseline | virtual | 1× | 1.00 | 8.33 | 2/3 | 7 | — | 6.43 |

Per episode (lines / new holes), selected policy vs baseline at 2× on the actual clock: level 1 7/−1 vs 8/−1,
level 3 4/1 vs 6/2, level 5 6/1 vs 3/4. All runs replay without model calls (`sol replay tetris`) with every
issued screenshot hash and final board matching.

What the comparison says:

- **Placement quality is at the baseline's level.** On the actual clock the selected policy clears as many lines as
  the true-board heuristic and leaves fewer holes; one of 55 applied decisions created a hole the baseline would
  have avoided. The side-by-side replay renderings (`scripts/tetris_render.py`) are the evidence to look at.
- **The fixed-case gain did not transfer.** `v12c` made the well-filling decision in the live level-5 episode (one
  vertical I, three rows) but its longer rule text lengthens every answer (median 416–443 output tokens against
  279–368) and every call by 1–1.5 s. After that clear the level rose to 6 (0.26 s per row) and the next three
  answers, 6.9–8.9 s wall, arrived after their pieces had locked; the three untouched pieces produced 14 holes.
  The candidate is retained as rejected: in this loop a longer policy is a slower policy, and slower loses at the
  levels where it matters.
- **The simulation is harsher than the live run** for the same policy: the registered profile (71 samples from the
  earlier, longer prompt; median 5.9 s, p90 7.8 s) has a heavier tail than the current transport (live median
  5.3 s), and its draws killed the level-5 episode of both Claude simulations after a four-row clear raised the
  level to 6, while the rules baseline under the same draws survived with a lower stack. Re-measuring the profile
  with `sol profile tetris` on the retained inputs is the first follow-up.
- **Normal speed is latency-bound**, for the baseline as much as for the model: at 1× both lose the level-5 episode
  and clear about one line per minute.

Next: a re-measured profile for the current prompt, more seeds at 2× (three episodes are not a tight estimate),
voting over repeated reads for the one-in-five height misreads, and a stronger reader at the same latency.
