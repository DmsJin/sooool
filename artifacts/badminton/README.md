# Badminton validation

## Goal-v2 migration and realtime diagnostic: 2026-10-17

[The goal-v2 record](realtime-goal-v2-20261017.json) identifies the single-goal
controller migrated from `badminton_sol_target_api20_gpu_001`. One actual API
Ultrafast match at L1/S3/seed101 finished 1:11, with legal serves 2/2 and legal
returns 8/19. All 5512 steps match native replay. The video preserves 165.36 seconds
at 100/3 FPS with English summaries from the same API decisions.

The run exposed seven initial strokes and one correction silently discarded while
the native planner was busy. The current code queues these commands and retains
their absolute contact times. It passes 21 GPU tests and 31 subtests. The completed
1:11 match predates this correction. Two corrected reruns stopped before a valid
decision; the latest raw provider reply reports `credit_balance_exhausted`.
Corrected realtime performance remains unmeasured. No policy score gain is claimed.

[Watch the completed diagnostic](../../outputs/sooool_badminton_goal_realtime_001/api-s3-101/index.html)
and [read the current report](../../outputs/sooool_badminton_goal_realtime_001/REPORT.md).
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

[Watch the S3 video with English summaries](../../../outputs/badminton-realtime-20261017/api-s3-101/index.html).
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

The [S2 video and English decision panel](../../../outputs/badminton-realtime-20261017/api-101/index.html)
use a verified native replay, 50 FPS and the actual 53.38-second S2 duration.
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

The local [video report](../../runs/badminton-validation/gpu/index.html) and raw
evidence are in ignored `runs/`. Each fresh run retains its actual source
snapshot. Full original camera images and transport records remain on the GPU
server at `/home/ubuntu/auto-research/lxy/outputs/sooool_badminton_port_001`.
No policy was promoted.
