# SOL researches a visual Tetris policy

The working object is one placement per piece, read from a plain game screen, executed by a key script that never
looks at the board. The research question was the same as for the other games: can a frozen visual model keep a
real-time game under control while its own answers are late. The loop was **observe a failure → change one thing
→ freeze → compare on fixed screenshots → run closed-loop episodes → keep or reject**, with every rejected
candidate retained in [`artifacts/tetris/development/assessments.jsonl`](../artifacts/tetris/development/assessments.jsonl).

Two provenance classes are kept apart below. **Development harness** numbers come from the scratch harness used
before the portable runner existed (Haiku-derived clip states, constant assumed 1.5 s delay unless stated). **Fresh
portable** numbers come from `sol simulate/eval tetris` in this repository and are the ones registered in
[`artifacts/tetris/evaluations.jsonl`](../artifacts/tetris/evaluations.jsonl).

## 1. Measure the workload before trusting a score

The first protocol asked for six placements per screenshot (current piece plus a five-piece preview) and assumed a
1.5 s delay. Under that assumption Haiku appeared to beat the rules baseline (11.3 vs 8.4 lines per 10 s clip).
The assumption was wrong: a strictly serial measurement of the same request took Haiku 40–46 s (about 9,000
reasoning tokens) and Sonnet 20.5 s. The result was discarded. Every later comparison uses a measured profile.

| Transport, one placement per request, plain screen | Serial wall delay | Fixed-set accuracy (set2, 43 states) |
|---|---:|---:|
| Claude Sonnet, low effort | 8.5 s | 57% |
| Claude Sonnet, medium effort | 11.1 s | 62% |
| Claude Opus, low effort (selected) | 6.5 s | 78% |
| Claude Fable 5.1, low / medium / high effort | 4.7 / 16.1 / 18.8 s | 46% / 63% / 75% |
| GPT-6.1-sol via `runtime/subscription.py`, priority tier | ~6 s (3–8 s) | 98% |

Accuracy counts an answer as acceptable when it is one of the placements with the fewest new holes on that board.
The ChatGPT subscription cannot open the ultrafast tier (the transport refuses rather than falling back), so the
~1.5 s delays of the paid Asterix/Rhythm runs are not available on a subscription. GPT runs were stopped at the
user's request after the measurements above; the Claude transport is the selected condition here.

## 2. Make the game screen and the executor honest

Early candidates annotated the screenshot (column numbers, later row numbers) and executed placements with a
controller that read the piece position from the engine. Both were withdrawn: the actor must read the raw game
screen, and the executor must work from the answer alone. The declared executor rotates, moves and hard-drops by
key presses computed from `{piece, rot, col}` and the published spawn rule; stale answers are discarded; spawns are
detected from the public screen. The rules baseline reaches identical placements through the same key scripts
(`tests/test_tetris.py`), so the executor adds no placement knowledge.

## 3. Fixed screenshots: hole mistakes have two causes

A 60-state development set (44 avoidable-hole decisions, 16 correct decisions) and a 43-state held-out set were
built from closed-loop failures. Reading the model's one-sentence public reasons separated two failure kinds:
knowingly accepting a gap when a gap-free spot existed (28/48), and misjudging a fit by one row (16/48).

| Candidate (Sonnet low, set1 ×3) | Acceptable | Old-error cases | Old-correct cases | Output tokens |
|---|---:|---:|---:|---:|
| v2 baseline with public reason | 103/180 | 59/132 | 44/48 | 748 |
| v3a: gap-free-first rule | 113/180 | 68/132 | 45/48 | 786 |
| **v3b: rule + gap-free height-pattern table** | **128/180** | **82/132** | **46/48** | **616** |
| v3c: rule + reason must state heights | 114/180 | 71/132 | 43/48 | 817 |

v3b was kept. Later candidates on the held-out set did not move it: model-authored memory notes (+2.7 points, within
noise, two drafts), same-screenshot voting (3-of-5 majority +5 points for 5× calls), and a rewritten fit rule for
Opus (100/129 vs 100/129). The prompt stayed within 5 KB; latency is dominated by reasoning tokens, not input.

## 4. Closed loop: decision quality is not the bottleneck

Development harness, 18 clips × 30 s, constant 1.5 s delay, one placement per request:

| Actor | Lines | New holes | Alive | Avoidable-hole decisions |
|---|---:|---:|---:|---:|
| Rules baseline (true board) | 6.50 | 1.39 | 18/18 | — |
| Sonnet low, v3b | 5.89 / 5.61 | 1.33 / 2.11 | 18/18 | 9% / 13% |
| Opus low, v7 (plain screen, key executor) | 5.72 | 1.33 | 18/18 | 9% |

Two protocol candidates were rejected on principle rather than score: two placements per answer (9.8 lines but 4.8
holes and two deaths, and the second piece never sees a screen) and an early-request executor that hovers the
positioned piece until the next answer (zero holes for the rules baseline at 2× but only 0.5 s saved at 1×, because a
one-piece preview makes every placement depend on the previous one).

## 5. Transfer to an actual clock

Development harness, serial real-clock runs, 18 clips × 30 s, normal speed:

| Actor | Capture→apply median | Lines | New holes | Alive |
|---|---:|---:|---:|---:|
| Opus low, v7 | 5.9 s | 0.56 | 9.0 | 12/18 |
| GPT-6.1-sol low, repository subscription transport | 5.8 s | 0.67 | 10.2 | 11/18 |
| Rules baseline with the measured profile | ~6 s | 0.67 | 9.5 | 12/18 |

All three fail the same way at levels ≥ 3: the piece locks before the answer arrives and the key script moves the
next piece instead. Reading the board was not the problem (GPT reads it correctly 98% of the time). Running 18
clips concurrently inflated the delay to 20 s and was discarded as an invalid condition.

With a declared 2× slowdown the same transport recovers: Opus low, 18 clips, real clock, 2.44 lines, 3.06 new holes,
17/18 alive, capture→apply 3.1 game seconds; the rules baseline under the sampled profile at 2× leaves 1.1 holes
with 18/18 alive. A 3× slowdown added nothing over 2×.

## 6. Aligning the loop with Asterix

A first portable version (`v8-keys`) captured a screenshot whenever a piece spawned and sent one image per request.
That is not how the other games in this repository observe, so it was replaced before registering results, and the
old runs were discarded rather than kept beside incomparable ones:

- **Fixed observation ticks**, as in Asterix: the screen is sampled every 60 frames (one game second) into a 9-tick
  window; a request is captured at the first tick after the previous reply arrived and its keys were pressed; the
  other ticks are counted as drops. The piece in play is therefore photographed mid-fall, not at spawn.
- **Three timestamped images** per request (oldest, middle, newest of the window) with their frame numbers, and the
  actor's own applied placements with ages in frames, in Asterix's request form.
- **Asterix's system text verbatim** and its task-prefix form: protocol, the profile's mean/median/P95 delay in game
  time, "the actual delay of your request is unknown", the simulation/real-time sentence swap.
- **No labels on the screen** (column numbers had been drawn on the screenshots) and **no piece letter in the
  answer**: the executor reads the falling piece's colour from the public spawn rows; the actor answers only
  `{"rot", "col", "reason"}`.
- **A one-line game description instead of a page**: `v11-short` keeps the action encoding, the gap-free-first rule
  with a corrected definition of a hole (an empty cell under a filled one is unusable *until the rows above it are
  cleared*, not forever), the fit table and the shape table, and nothing else.

Single episodes were run after each change until the scheme was fixed; the 3-episode validation below is the only
multi-episode evidence of this lineage.

## 7. Two decisions the model gets wrong, on fixed screenshots

Watching the selected policy's full game (seed 0, level 1, from an empty board) showed two recurring misplacements.
Both were cut out as fixed cases (the exact request text and three images of that moment) and re-asked five times
per prompt variant; scoring is new holes and rows completed by the answered placement on the true board.

| Case | True heights | Rules baseline | `v11-short` | `v12-tradeoff` | `v12b-tradeoff` | `v12c-tradeoff` |
|---|---|---|---|---|---|---|
| 15: O, stack 1-3-4-7-7-8-8-8-7-8 | misread the 3/4 step | O on 0-1 (one hole) | 5/5 gap-free on 3-4 | 4/5 (one misread) | 5/5 | 4/5 (one misread) |
| 28: J, well in column 3 beside 5-high stack | fill the well | vertical J in the well: one hole, two rows | 1/5 fill the well, 4/5 play safe | 3/5 fill (two illegal reads) | 0/5 fill | 4/5 fill, 1/5 safe |

Case 15 is a reading error: about one answer in five mis-counts a column height by one, with every prompt, and the
answer is then internally consistent with the wrong reading. No prompt changes this; only repeated reads (voting)
or a stronger reader would. Case 28 is a rule the prompt imposed: `v11-short`'s "accept a gap only when no gap-free
spot exists" forbids the well fill that completes two rows. `v12c-tradeoff` adds the one exception (two or more
completed rows are worth one hole; check the deepest well first; do not hold a well open beside a five-high stack)
and fixes the decision four times in five without hurting case 15. `v12` (a longer rewrite) and `v12b` (the
exception without the well check) did not.

## 8. Fresh portable validation (three episodes)

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
