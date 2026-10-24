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

## 6. Fresh portable validation

The runner, policy `v8-keys` (v7 with the timing sentence filled from the profile and mode), profile and recipes in
this repository were frozen and run with `sol simulate tetris` and `sol eval tetris` on the recipe's fifteen
60-second episodes (three seeds × start levels 1–5, 20 rules-placed pieces before the clip). These are the registered
numbers; see [`artifacts/tetris/README.md`](../artifacts/tetris/README.md) for the run directories and replay checks.

| Run | Provider | Clock | Slowdown | Lines | New holes | Height Δ | Alive | Stale | Capture→apply (game s) |
|---|---|---|---|---:|---:|---:|---|---:|---:|
| `claude-eval-2x` **(selected)** | Claude Opus low, stateless CLI | wall | 2× | 4.73 | 3.33 | +28.8 | 14/15 (one level-5 death) | 4 | 3.0 (wall median 5.97 s, p90 7.94 s) |
| `claude-sim-2x` | Claude Opus low | virtual, sampled profile | 2× | 4.87 | 1.33 | +26.0 | 15/15 | 0 | 3.0 |
| `rules-sim-2x` | rules baseline (true board) | virtual, sampled profile | 2× | 6.00 | 1.33 | +14.7 | 15/15 | 0 | 3.0 |
| `claude-eval-1x` | Claude Opus low | wall | 1× | 0.93 | 5.47 | +36.4 | 12/15 (three level-5 deaths) | 17 | 5.8 |
| `claude-sim-1x` | Claude Opus low | virtual | 1× | 1.27 | 6.40 | +32.1 | 11/15 | 25 | 5.9 |
| `rules-sim-1x` | rules baseline | virtual | 1× | 1.80 | 4.67 | +23.7 | 12/15 | 21 | 5.9 |

Means over the 15 episodes (60 game seconds each). All six runs replay without model calls (`sol replay tetris`),
with every captured screenshot hash and final board matching. Reading: at 2× the selected transport keeps every
start level under control and clears lines at about 80% of the true-board baseline's rate; on the actual clock it
leaves more holes than in simulation (3.3 vs 1.3) because real delays cluster differently from the sampled ones
and four answers arrived after their piece locked. At normal speed the same policy, the simulation and the rules
baseline all fail level 5 and clear almost nothing: the condition is latency-bound, not policy-bound. The wall
delay of the portable transport (median 5.97 s) matches the profile it was told (5.9 s).

The next research questions are more seeds and repeats at 2×, a measured profile from `sol profile tetris` on the
portable transport, long-tail sensitivity, and whether an executor that waits for the next answer before dropping
can be justified without a second request in flight. Each belongs in a new evaluation record.
