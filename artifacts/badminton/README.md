# Badminton validation

## Completed realtime rerun: 2026-10-17

The [rerun record](realtime-rerun-005.json) retains one actual API match using
`tactical-goal-v2`, seed 101, L1/S3, and serial `gpt-6.1-sol / low / ultrafast`
requests. All 47 provider receipts confirm Ultrafast. The match completed and
lost 8:11. The policy remains unpromoted.

| Run | Score | Legal returns | Legal serves |
|---|---:|---:|---:|
| Prior fixed tactics | 8:11 | 57/64 (89.1%) | 5/9 |
| Prior SOL | 5:11 | 36/45 (80.0%) | 4/6 |
| SOL rerun | 8:11 | 90/97 (92.8%) | 5/9 |

The rerun used the same execution code and protocol as the prior SOL match.
It added one SOL match, with no new fixed-tactics match, profiling or simulation.
All 90 controlled rally strokes used SOL goals, with zero rule fallbacks.
The audit separates 38 planned exact goals and 52 legal projections.
Four serves failed. This observed single-match improvement does not promote
the policy or establish a repeated success rate.

The protocol used 100 Hz game physics, observations up to 10 Hz game time,
and 100/3 control steps per wall second. The RTX PRO 6000 Blackwell Server
Edition GPU used EGL, driver 615.71.09, Python 3.11.17 and MuJoCo 3.3.7.
The environment revision was `da1f787f775ea6524d698c0b063157ded4c0fef9`.
Execution used base `06633f3b911da6bce57e8bd618ac1a0a6907e01d` plus the
retained run's uncommitted source snapshot. Later PR changes are not attributed
to this recorded match.

The retained prompts included internal installation acknowledgements in 28 of
47 requests. The current public-input filter excludes those acknowledgements
from future model inputs. This recorded result predates that input correction.

The match completed 276.09 game seconds in 828.27 wall seconds. The native
replay matched all 27,609 steps, and the recorded clock passed its limits.
All 47 requests settled for $6.5010948. Mean complete-JSON readiness was
2.251 seconds, with P95 3.131 seconds. The shared comparison ledger retained
$10.1178768 cumulative spend under its $15 cap.

[Watch the 15-second opening serve and rally](../../assets/gameplay/badminton.mp4).
The excerpt is source seconds 6–21, with original S3 speed, both cameras, and
same-response English summaries. The opening point ultimately finished 1:0;
the short excerpt shows its beginning. The full 13:48.27 video is a verified
native replay of actual API controls at 100/3 FPS, rendered without model calls.

Primary evidence remains under the local artifact directory
`outputs/sooool_badminton_realtime_rerun_005/`: `REPORT.md`, `protocol.json`,
`source.tgz`, `comparison.json`, and the `sol-s3-101/` summary, audit, requests,
source snapshot and `realtime-s3.mp4`. Raw camera images remain with the original
GPU-host artifact directory. The committed rerun record contains compact audit,
timing and per-request tier evidence for review without those local files.

## Goal-v2 migration and realtime diagnostic: 2026-10-17

[The goal-v2 record](realtime-goal-v2-20261017.json) identifies the single-goal
controller migrated from `badminton_sol_target_api20_gpu_001`. One actual API
Ultrafast match at L1/S3/seed101 finished 1:11, with legal serves 2/2 and legal
returns 8/19. All 5512 steps match native replay. The video preserves 165.36 seconds
at 100/3 FPS with English summaries from the same API decisions.

The run exposed seven initial strokes and one correction silently discarded while
the native planner was busy. A subsequent correction queued these commands and
retained their absolute contact times. That correction passed 21 GPU tests and
31 subtests. The completed 1:11 match predates it. Two initial corrected reruns
stopped before a valid decision; the latter provider reply reported
`credit_balance_exhausted`. The later completed comparison and rerun are recorded
above. This earlier diagnostic does not establish a policy score gain.

The diagnostic video/report are local-only at
`outputs/sooool_badminton_goal_realtime_001/api-s3-101/index.html` and
`outputs/sooool_badminton_goal_realtime_001/REPORT.md`; they are not included in
this checkout. The [compact record](realtime-goal-v2-20261017.json) is available here.
All new evidence stays separate from the earlier S2/S3 episodes below.

## S3 realtime API retry: 2026-10-17

[The S3 record](realtime-s3-20261017.json) retains one seed-101 L1 episode over
base `bf64281`, its actual source snapshot and the pinned native environment.
The same RTX PRO 6000 GPU ran `gpt-6.1-sol / low / ultrafast` with serial API
requests. Only the slowdown changed to S3; the wall limit scaled to 900 seconds
to preserve the 300-game-second limit. Native planning still requests 0.4 wall
seconds, rounded up to 14 native control steps (0.42 wall seconds).

| Actual API episode | Score | Legal serves | Legal returns | Deadline plan discards | Calls | Cost |
|---|---:|---:|---:|---:|---:|---:|
| S2 | 0:11 | 0/1 | 0/10 | 9 | 20 | $1.945110 |
| S3 | 0:11 | 1/1 | 16/27 | 4 | 67 | $8.239782 |

S3 completed 74.59 game seconds in 223.77 wall seconds. It accepted 59 intentions,
applied 17 SOL-linked rally plans, changed four rally plans and changed 21 recovery
commands. Every request settled; cumulative S2/S3 cost was $10.184892 under the
$20 limit. Both episodes lost, and the policy remains unpromoted.

The S3 replay matches all 7,459 control steps. Its initial audit exposed a
same-step event-order bug at frame 3450: the live loop applied a control before
capturing, while the auditor checked the capture first. The corrected auditor
passes a native regression test and also retains exact S2 replay. The initial
failure log and corrected auditor source remain with the raw evidence.

The S3 video with English summaries is local-only at
`../outputs/badminton-realtime-20261017/api-s3-101/index.html`, relative to the repository root.
It preserves the actual S3 duration at 100/3 FPS and uses no new model calls.

## Actual realtime API: 2026-10-17

[The realtime record](realtime-api-20261017.json) identifies the implementation over
base `bf64281`, its source snapshot and the pinned environment. One seed-101 L1
match used actual `gpt-6.1-sol / low / ultrafast` API decisions at S2. It finished
0:11 after 26.69 game seconds / 53.38 wall seconds. All 20 requests settled for
$1.945110. The native replay matched all 2,669 control steps. Clock P99 lag was
0.614 ms and maximum lag was 44.916 ms.

Gameplay failed: legal serves 0/1, legal returns 0/10. Nine intentions were accepted,
but no applied rally plan linked to an SOL intention. Nine native planning jobs
missed the fixed 0.4-second preparation deadline. They returned a mean 0.591 wall
seconds after that deadline, with a maximum 0.8 seconds. Physics kept advancing.
This record retains the original S2 episode; the later S3 retry is reported above.

The local-only S2 video and English decision panel at
`../outputs/badminton-realtime-20261017/api-101/index.html` use a verified native replay, 50 FPS and the actual 53.38-second S2 duration.
Public summaries appear at their recorded intention-acceptance times. Complete
local records are under `../outputs/badminton-realtime-20261017` relative to the
repository. Full camera inputs remain in the remote evidence directory named by
the JSON record. The Python 3.12 suite passed 47 tests with two native tests
skipped; the GPU runtime passed all 26 relevant tests, including native coverage.

## Subscription/profile transfer

[GPU validation](gpu-validation-20261017.json) records the local port over SOOOOL
base `dc4eae7` and the original `source_tactical_005` checkpoint. The external
environment is pinned to `da1f787f775ea6524d698c0b063157ded4c0fef9`.
[Historical development totals](historical-tactical-003.json) remain separate.

Validation used an RTX PRO 6000 Blackwell GPU, Python 3.11.17 and MuJoCo 3.3.7.
The protocol was L1/S2, 100 Hz physics, up to 10 Hz public observations, seed 101,
and two fresh 60-game-second windows. Rendering and local decision costs remained
charged. Subscription Fast was disabled. The retained 100-call API Ultrafast
profile supplied virtual delays; no new paid API calls were made.

| Fresh window | Score, ours:opponent | Legal returns | Actual model generations |
|---|---:|---:|---:|
| Rule reference | 3:1 | 18/19 | 0 |
| SOL with profile | 0:6 | 16/22 | 47 |

Both native replays matched. SOL supplied 40 accepted intentions, changing 12
rally choices and 23 recoveries. Both windows had zero invalid actions and zero
timing rejections. This verifies functional transfer and sustained legal play.
The SOL window scored below the reference. These windows do not establish a
full-match win rate or a SOL advantage.

Two original 60-second traces also replayed exactly: rules 3:5 and SOL 2:8.
They used saved actions and made zero model calls. One earlier native preflight
attempt rejected the default-tier `null` echo before generation. Its partial
record is retained and excluded from the scored pair.

The full repository suite passed 44 tests under Python 3.12. The GPU runtime
passed 21 relevant tests and 16 subtests under Python 3.11. Existing Touhou code
requires Python 3.12 syntax and was left unchanged.

The local video report at `runs/badminton-validation/gpu/index.html` and raw
evidence are in ignored `runs/`, not included in this checkout. Each fresh run retains its actual source
snapshot. Full original camera images and transport records remain on the GPU
server at `/home/ubuntu/auto-research/lxy/outputs/sooool_badminton_port_001`.
No policy was promoted.
