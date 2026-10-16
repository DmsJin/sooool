# Touhou Sol study: interim results

This is an ongoing experiment, not a solved-task claim. The acceptance condition
is `won` in the unchanged game at 1x under actual API response time, with the game
advancing throughout inference. `survived`, slower speeds, and simulated API
delay do not satisfy that condition.

All subscription development decisions come from actual gpt-6.1-sol/low visual
requests. Diagnostics and deterministic action replay are used only for offline
analysis; the executor never converts estimated coordinates into movement.

## Completed development conditions

Remote evidence root: `/home/ubuntu/wzh/touhou-sol-study` on the authorized Ubuntu
experiment host. Each round keeps frozen source, config, PNG inputs, prompts,
responses, and applied actions. Seeds below are 2/5/6 in that order.

| Round | Speed | Wins | Outcomes / remaining HP |
| --- | --- | --- | --- |
| serial-maneuver-v1-retry1 | 1x | 0/3 | lost 1225; survived 830; lost 1255 |
| serial-impact-v1 | 1x | 0/3 | survived 320; lost 950; lost 380 |
| serial-grounded-v1 | 1x | 0/3 | lost 585; survived 290; survived 185 |
| macro-intro-v1 / macro1x | 1x | 0/3 | lost 1150; survived 565; lost 1520 |
| macro-intro-v1 / introSingle | 1x | 0/3 | lost 945; survived 510; lost 490 |
| macro-intro-v1 / macroHalf | 0.5x | 3/3 | won at 42.95s / 44.55s / 47.52s |
| schema-macro-v1 | 1x | 0/3 | lost 1510; survived 265; survived 265 |
| schema-single-v1 | 1x | 1/3 | won at 59.47s; survived 90; lost 435 |
| macro-speed-v1 / macro075 | 0.75x | 0/3 | lost 15; lost 875; lost 195 |
| macro-speed-v1 / macro090 | 0.9x | 2/3 | won at 59.30s; survived 35; won at 45.55s |

Half-speed wins took 539–574 wall seconds. Two complete serial-grounded games
took 675–679 wall seconds and 29–31 model calls. More recent schema-macro complete
games took 261–264 wall seconds. Subscription timing is variable; these conditions
also differ in prompts, request count, caching, and concurrent load.
The first 1x single-action win took 337 wall seconds, with zero invalid actions.
The speed sweep is not monotonic; three seeds and stochastic decisions are too
small a sample to establish a reliable speed-to-success curve.

## Latency and cost

All paid profiling has been strictly serial. Total settled paid spend after the
single-action schema profile was USD 2.835201; no real-time paid game had yet run.
The overall authorized cap remains USD 30, including profiling and verification.

Changing-observation, three-image full-response API latency:

| Profile | Valid samples | Median |
| --- | ---: | ---: |
| profile-macro-v1.jsonl, compact matrix macros | 16/18 | 1.426s |
| profile-schema-v1.jsonl, named action macros | 18/18 | 1.783s |
| profile-schema-single-v1.jsonl, named single action | 9/9 | 1.504s |
| profile-final-single-v1.jsonl, actual finalist inputs | 18/18 | 1.843s |

Finalist recalibration additionally included three original intro observations;
all 21 requests were valid. Changing-game P95 was 2.586s. The mean settled cost
across all 21 requests was USD 0.0294822. Cumulative settled spend after this
recalibration was USD 3.4543272, with no real-time paid game run yet.

Intro single-image samples are recorded separately and excluded from these
three-image medians. Repeated identical-image hot-cache results are not used as
the changing-game latency condition. Schema adds output and input overhead but
eliminates observed missing/invalid action fields in the schema-macro full round.

In an early 45-decision sample from macro-intro-v1, subscription median total was
11.370s, action RPC 11.249s, thread preparation 0.111s, and image preparation
0.006s. These medians describe that sample, not an invariant provider latency.

Research simulation previously redrew frozen frames while awaiting model calls.
The idle rendering fix removes that avoidable CPU work while preserving draws on
manual stepping/capture and all real-time rendering. It does not alter the engine.

Optional lean native context replaced irrelevant coding instructions and disabled
unneeded tools. One same-input smoke reduced input tokens 15733 to 8476, but did
not establish a latency improvement (6.51s versus 6.31s, different cache states).
It is a separate development condition, not a retroactive change to old runs.

## Evidence-guided next experiments

Recorded-action replay reproduced final tick, HP, and hits for six analyzed
episodes. Original engine SHA256 remains
`348e81340d4a09f8b488193daf0b4e395afa2755d34f249585ff5e1ffe787aa4`.

1. Half-speed success is primarily better timely horizontal tracking: in seed5,
   at tick2100 the half-speed boss had 650 HP versus 1775 in the 1x macro game.
   The final upward movement began after that advantage was established.
2. Invalid compact actions can discard an entire multi-action response, including
   its bomb. Named schema actions address protocol loss, not strategic quality.
3. During bomb flash, an original macro decision reported the older image's
   player x=228 while the newest image's player was approximately x=180.4.
   `grounded_latest` tests using the last image for current position and older
   images only for motion. Model estimates remain audit-only.
4. Bomb decisions can arrive after collision or while dying. A held X does not
   create a fresh press edge on respawn. Preventive bomb timing is a separate
   proposed policy condition.

Running rounds at this checkpoint: `schema-single-v1`, `macro-speed-v1` (0.75x and
0.9x), and `latest-grounding-v1` (1x single/macro latest-image prompts with a lean
macro control). Finalists must be independently confirmed, serially recalibrated,
and tested with real API timing before any solve claim.

Later checkpoint: the single and speed rounds above are complete. The frozen
single-action finalist is being independently rerun as `confirm-single-v1` with
the final profile and fresh delay seeds 3115/3118/3119. `guard-v1` tests preventive
bomb timing independently. Real-time capture/apply auditing now records the
browser's actual timestamps, speed, pause flag, and maximum rAF gap; this changes
evidence logging without changing physics or movement decisions.

## First real API attempt

`api-real-single-v1-seed1` used the frozen single-action policy, actual API calls,
and uninterrupted real-time speed 1. It lost at tick3239 (53.983 game seconds),
with boss HP450, three hits, and zero bombs. All 25 requests were valid; 24
responses were applied before termination. Cost was USD0.866700. API median was
1.638s and mean1.733s, consistent with the calibrated latency condition.

The browser clock at termination measured visual_frame3674 / wall61258.9ms,
actual_visual_speed0.999583, max_rAF_gap66.7ms, zero blur events, and paused=false.
The summary wall time62.803s also includes browser startup and is not the speed
denominator. The original intro/spell declarations account for435 visual frames
outside logical gameplay. Original game-over and a full video were retained.

The final-profile independent subscription confirmation completed 0/3 wins:
survived HP725 / HP165 / HP475. Thus the original 1/3 result did not establish a
stable policy. Real API attempts continue under the same frozen policy in seed
order1,7,8; all outcomes are retained. This first failure is not a solve claim.
