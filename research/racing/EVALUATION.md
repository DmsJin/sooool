# How SOL reached the selected Racing policy

This is a focused, retrospective record of the path to **lane-commit-v14**, an early selected checkpoint. It is not an exhaustive chronology or a claim of the latest/best development result. SOL's coding agent changed task prompts, action representations and scheduling/controller code, then evaluated returned gameplay decisions against the simulator. The user supplied constraints, selected the minimal outer prompt, chose this checkpoint and requested the video format. No model weights were trained.

The meaningful research loop is: **observe a failure → propose a change → run a fixed seed group under delay → inspect full results and replay → freeze a candidate → test new seeds → transfer to continuously advancing API gameplay**. The gameplay model is SOL; the development agent’s code/prompt changes and evaluation gates are recorded separately from gameplay actions.

## Iteration record

| Step | Hypothesis / change | Observed result | Decision and evidence |
|---|---|---|---|
| Establish latency | Measure direct API decisions serially before parallel development. | 32 calls; fastest 0.984s, median 1.350s, P95 2.258s. | Retain full empirical distribution, including its tail. [Profile and raw measurements](../../profiles/racing/) |
| Reduce outer prompt | Keep the game task/observations/schema and simplify the Codex wrapper. | 24 interleaved pairs: median 8.206 → 12.317s; no speedup established. | User selected minimal outer anyway; do not narrate it as a measured optimization win. [A/B](evidence/outer-prompt-ab.json) |
| Bounded waypoint + speed cap | Use finite model targets and coded curvature limiting to stabilize delayed driving. | 0/3 full development matches at 1x. | Reject this checkpoint for acceptance. [Group and per-episode records](evidence/round9_curve_cap/) |
| Visual lane goals | Ask SOL for target speed, stripe-relative lane offset and lookahead; track at 5 Hz. | 2/3 development matches. | A useful direction, but inconsistent. [Records](evidence/round10_visual_lane/) |
| Commit to a lane | Explicitly define stripe-relative offset; keep lane while overtaking; avoid switching merely for a bend. | 3/3 development seeds 101/111/121. | Freeze lane-commit prompt and executor for confirmation. [Exact prompt](../../policies/racing/lane-commit-v14/prompt.txt), [records](evidence/round11_lane_commit/) |
| Frozen confirmation | Test fresh seeds 301/302/303 with the frozen candidate. | 3/3 matches, matching independent replay. | Retain separate confirmation cohort. [Records](evidence/round13_lane_commit_holdout/) |
| Real-time transfer | Run actual API on seed304; let wall-clock physics continue during inference. | **2:0 win**, 82 API calls; 51.79 game seconds / 51.795 wall seconds. | Genuine Level 1 hybrid real-time validation. [Summary](evidence/api-live-lane-commit-1x-s304-v1/summary.json), [identity/image/control audit](evidence/api-live-lane-commit-1x-s304-v1/audit.json) |
| Public explanation video | Preserve the lane controller; add English summary before action in each API output, issue every 0.6s. | **2:1 win**, 137 API calls; 85.97 game seconds / 85.979 wall seconds. | Separate output variant; repeat of seed304, not another untouched holdout. [Summary](evidence/api-live-lane-summary-1x-s304-v1/summary.json), [video audit](evidence/api-live-lane-summary-1x-s304-v1/decision_video_audit.json) |

**Historical input correction:** the subscription adapter used for the waypoint/lane groups omitted image contents (`localImage detail=low`). Numeric camera measurements still reached SOL. Their group results/replays are retained as numeric-feature hybrid development, **not visual-subscription success**. The corrected adapter now uses `detail=auto`; no new successful subscription replication is claimed here. Direct API inputs bypassed that bug; the real API seed304 image hashes and returned model/tier were verified. This limits how strongly the historical development groups predict current visual behavior.

The earlier lane-goal checkpoint also had a real API seed204 2:0 win; its [separate record](evidence/api-live-lane-1x-s204-v1/) is retained rather than conflated with lane-commit seed304.

## What the real-time records establish

| Variant | Seed | Match | Actual API calls | Commands applied | Integrity |
|---|---:|---:|---:|---:|---|
| Frozen action-only lane-commit | 304 | 2:0 | 82 | 260/260 | Canonical valid trial and deterministic replay |
| Same-response English summary + lane-commit | 304, reused | 2:1 | 137 | 432/432 | Canonical valid trial and deterministic replay |

Both are actual `gpt-6.1-sol / low / ultrafast` API runs with legal camera inputs, Level 1, 1x physics, no imposed model delay and zero own warnings. Winning heats finish normally through all checkpoints. The simulator/referee/reward were not changed. Replay verifies trajectory consistency; the model-versus-baseline comparison is reported separately below. Streaming releases valid complete JSON before response drain when identity is already known, while retaining accounting/occupancy until completion.

## Recorded GPT and no-GPT comparison

**The selected GPT-guided strategy won 7/7 recorded matches on the seven tested seeds; the fixed grid-aware no-GPT baseline won 3/7.** Both use the same lane-controller class and camera metrics. On seeds 111, 121, 301 and 303 the baseline lost and the GPT-guided strategy won. This is positive evidence for the GPT-guided strategy’s performance in this tested setup; a controller that sometimes wins alone does not account for the full observed result.

| Seeds | Fixed grid-aware baseline | Selected GPT strategy | GPT execution / evidence |
|---|---:|---:|---|
| 101 / 111 / 121 | 1/3 | 3/3 | Subscription + sampled API delays; [development records](evidence/round11_lane_commit/status.json) |
| 301 / 302 / 303 | 1/3 | 3/3 | Subscription + sampled API delays; [frozen confirmation records](evidence/round13_lane_commit_holdout/status.json) |
| 304 | 1/1 | 1/1 | Actual continuously advancing API; [selected result](evidence/api-live-lane-commit-1x-s304-v1/summary.json) |
| **Recorded total** | **3/7** | **7/7** | Same seven seeds; execution conditions differ across cohorts |

The baseline’s [per-seed outcomes](evidence/fixed-grid-baseline.json) match those seed groups. The six subscription results used numeric camera measurements because their historical image adapter omitted image contents, as disclosed above. The seed304 API run did receive images. The English-summary retake on seed304 is a separate successful variant, not an eighth seed in this total.

The baseline matches ran at 1× wall-clock physics with zero GPT calls, retaining the visual tracker, curvature cap, goal expiry and imposed historical API delays. The historical GPT cohorts were not rerun under identical timing and concurrent load, their goal parameters differ, and the rule baseline was not exhaustively tuned. Those limits constrain attribution of an exact effect size and generalization; they do not erase the observed 7/7 versus 3/7 result. A timing-matched comparison and more seeds would refine that result.

### Additional fixed-goal baselines

| Fixed-goal baseline | Match wins over seeds 101/111/121/301/302/303/304 | Observation |
|---|---:|---|
| Speed 3.2, lookahead 2.0, offset ±0.38 from each heat's initial grid | 3/7 | Fixed grid-aware reference for the 3/7 versus 7/7 comparison above. [Record](evidence/fixed-grid-baseline.json) |
| `[3.4, +0.38, 1.7]` every heat | 0/7 | Collision warnings; constant left offset conflicts with the opponent. [Record](evidence/fixed-plus038.json) |
| `[3.4, -0.38, 1.7]` every heat | 0/7 full matches; 7/7 first heats won | After grid exchange, second-heat collisions cause disqualification. [Record](evidence/fixed-minus038.json) |

The constant-offset variants did not win any complete matches. Their first-heat successes must not be counted as full-match wins or confused with the selected GPT strategy’s 7/7 complete-match results.

## Presentation and selection

The featured video contains all three heats from the summary variant; no later model generates commentary. The right panel and game view are reordered together from original heats **1/2/3 (loss/win/win)** to **2/1/3 (win/loss/win)**. A continuous disclosure names the original heat. The [edit audit](evidence/api-live-lane-summary-1x-s304-v1/edit_audit.json) records exact frame ranges. The evaluated result remains the original 2:1 match.

The selected release is deliberately narrow: one understandable policy, its development lineage, and independently replayed real-time evidence. It does not claim strict direct GPT steering, broad robustness or a fully autonomous search without human direction. See [record requirements](RECORDS.md) before adding a result.
