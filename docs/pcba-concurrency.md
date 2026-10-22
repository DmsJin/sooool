# PCBA inference concurrency and execution overlap

Concurrency is measured in two different experiments. They must not be confused
with the 200 Hz physics thread or the 20 Hz literal robot-command scheduler.

## Matched snapshot request benchmark

`sol latency pcba` sends fresh GPT-6.1 Sol Fast requests at concurrency 1, 2 and 4.
It uses eight identical public prompt/image snapshots per concurrency setting,
selected from the retained Fast trial. The order is reversed in the second block
(1/2/4 then 4/2/1) to expose warm/order effects. Each worker owns a separate native
Codex client; a client is never accessed concurrently. Authentication/setup is
outside the timed cohorts; quota checks, thread creation, inference and response
handling are included in the request timings. Original prompts, PNGs, new model
answers, tier confirmations and token/caching usage are retained.

These are real subscription inferences against frozen observations. Physics and
robot execution do not run in this benchmark, and it has no handling score.
The mean request latency is a request's completion minus its actual start.
The amortized reply interval is total cohort time divided by completed requests;
it measures throughput, not guaranteed regular cadence or observation freshness.
Eight requests per setting are a diagnostic sample, not a stable tail-latency SLA.

Retained local benchmark: `runs/pcba-concurrency-latency-v1`, 24 fresh Fast
requests, eight per setting, all valid responses:

| Concurrent requests | Mean request latency | Median | P95 | Cohort time / replies |
|---|---:|---:|---:|---:|
| 1 | 5.359 s | 5.340 s | 6.130 s | 5.361 s |
| 2 | 5.533 s | 5.426 s | 6.662 s | 2.829 s |
| 4 | 5.857 s | 5.697 s | 6.835 s | 1.674 s |

The last column is amortized throughput. It is not a fresh-camera control period.
Higher concurrency did not lower single-request latency in this small sample.

```bash
export SOL_CODEX_BIN=/absolute/path/to/codex
uv run sol env setup pcba
uv run sol latency pcba --source runs/pcba-policy-fast-v1 --output runs/pcba-latency-new
```

## Actual asynchronous pipeline

`sol pipeline pcba` overlaps visual inference with the current action chunk.
`--concurrency 1` already allows that overlap. `--concurrency 2` or `4` additionally
allows multiple inference requests in flight. Robot execution always has exactly
one lane. The model still chooses every literal delta, wait, vacuum operation and
fixture request; there is no automatic grasp/place or task recovery controller.

The model sees current public camera/proprioception/device observations, its own
selected memory, the committed chunk's literal segments and its expected final
commanded robot pose. This endpoint is computed only from already-issued robot
commands, not hidden object state. It plans subsequent deltas from that trusted
endpoint. It also declares desired start conditions for public vacuum, fixture
presence/clamps/tester and result ID switches.

A new chunk is admitted only after its parent finishes. Replies are rejected if
the parent was superseded or failed, the sequence is older than a selected reply,
the robot's command target does not match the expected start, a declared sensor
guard disagrees, or wall/simulation TTL has expired. A latest-ready valid reply is
selected; old replies cannot overwrite a newer plan. Unselected replies never
update memory. Guards validate model intentions; they do not choose destinations.
Unknown test results stay unknown, even when a parent is expected to finish.

```bash
uv run sol pipeline pcba --concurrency 1 --wall-seconds 120 --max-calls 24 --output runs/pcba-pipeline-c1-new
uv run sol pipeline pcba --concurrency 2 --wall-seconds 120 --max-calls 36 --output runs/pcba-pipeline-c2-new
```

The same Fast tier, seed, TTL and pipeline policy are used for both live checks.
The former serial run is a reference, not a matched statistical comparison of
handling success. Each live check is a short plumbing/control experiment, not a
five-board success-rate evaluation. Reports include request RTT, source age at
actual action start, intervals between usable chunk starts, inter-chunk idle
wait, overlap count, rejected/superseded replies, actual commands and task events.
These metrics show how much of the raw response throughput reaches the robot.
Native state snapshots and final images are saved for replay export without
online recording/render load beyond the actual policy observations.

Both local pipeline attempts remain **diagnostic**, not valid realtime comparisons:

| Run | Requests / replies / selected chunks | Mean request latency | Mean source age at chunk start | Sim / wall elapsed | Correctly sorted |
|---|---|---:|---:|---|---:|
| `pcba-pipeline-c1-v1` | 15 / 14 / 12 | 6.337 s | 8.330 s | 110.880 / 120.006 s | 0 |
| `pcba-pipeline-c2-v1` | 27 / 25 / 12 | 6.688 s | 8.281 s | 104.705 / 120.461 s | 0 |

Each tested one board. Both failed the 1% wall/physics drift gate. The second
reduced unnecessary monitoring polls, but still failed. It rejected 13 completed
replies and had two requests pending at stop; actual inference/execution overlap
was 16.071 seconds summed across request intervals. No realtime performance
improvement or task-success advantage is established. Changing polling between
these attempts also prevents treating them as a matched concurrency comparison.
Reports, native snapshots, source freezes and diagnostic assessments are retained.

More requests can improve response throughput while leaving each camera snapshot
several seconds old. Contact/testing dependencies can make speculative replies
unusable. Concurrency alone cannot turn multi-second inference into a millisecond
visual-feedback loop. The current stopped-board cell also has weak realtime task
pressure; see [the PCBA guide](pcba.md).

The [recirculating variant](pcba-loop.md) adds moving skewed boards, a bounded
pick window and explicit lap/batch deadlines. It uses the same guarded pipeline
with `--layout loop`. More outstanding calls cannot remove the need for motion
prediction and fresh contact feedback. Only the offline oracle demonstration
includes a coded pose/velocity tracker; the model runner does not receive it.

The subsequent four-way loop evaluation uses `--physics-process`, a 100 Hz loop
physics budget, one llvmpipe rendering thread, and `--continue-after-deadline`.
It is a new condition, not a matched comparison with the two earlier thread-clock
stopped-line diagnostics. The 150-second deadline remains latched while a bounded
600-second diagnostic continuation asks whether all five boards can finish.

## Latency tuning and staggered capture (2026-10-17)

All options keep the strict literal-action baseline: the model still chooses every
delta, wait, vacuum and fixture request. New `sol pipeline pcba` options:
`--output-mode lean` (summary <=80 chars, memory <=120 chars, <=4 decimals;
`policies/pcba/pipeline-lean.txt` and `pipeline-lean.schema.json`), `--image-size WxH`,
`--schedule stagger` (capture about one measured reply latency before the committed
chunk ends; with two lanes the first uses p80, the second p40; an idle robot sends one
request and hedges only after p80), and `--transport-tuning` (quota guard every 10
calls, 80% stop retained; the next native thread is prestarted). PNG encoding now uses
fast lossless compression. Per-call `stages_s` records setup, time to first answer
delta and output streaming.

Measured, small samples, not a stable SLA:

| Run | Condition | Mean request | Notes |
|---|---|---:|---|
| `pcba-loop-fast-c4-top-v1` (Codex) | top camera, c4 interval | 10.66 s | 51 requests, 11 chunks, 23 superseded |
| `pcba-loop-latency-tuned-c2-v1` | top 480x360, lean, stagger c2, tuning | 9.10 s | 22 requests, 9 chunks, 2 superseded; first answer delta 7.20 s, stream 1.89 s, setup 0.006 s; timing gate failed (max tick lag 23 ms) |
| `pcba-latency-attribution-probe-v1` | 5 frozen snapshots x 4 conditions | 11.6-15.3 s | 480x360 raised reasoning tokens (248 -> 327-372) |
| `pcba-latency-attribution-probe-v2` | 10 frozen snapshots, full vs lean+tuning | median 10.0 vs 10.9 s | lean won 4/10 pairs; 20-40 s server outliers dominate |

Conclusions: prestarting threads reliably removes about 0.5 s; staggering halves
requests per selected chunk; lean output shortens answers about 17% but did not
produce a robust latency gain; lower resolution is not recommended. Time to the first
answer delta (model reasoning, 7-12 s) remains dominant. Robot motion stayed about 3%
because chosen chunks are short and about a quarter of replies are rejected whole:
the model targets the 0.025 m per-command limit and lands slightly above it
(`Invalid translation`, 40/152 in `pcba-loop-fast-c4-v1`, 5/21 in the tuned run).

## Development simulation (virtual clock)

`sol simulate pcba --profile RUN_DIR` makes fresh subscription inferences (default
tier by default) on actual rendered frames, but physics advances only in a trusted
virtual-clock loop. Each reply becomes usable at capture time plus a delay resampled
from the profile's measured capture-to-reply seconds; if inference is still running,
the virtual clock waits. Draws never reach the actor. Results are development evidence,
not realtime or 1x claims. Defaults: loop layout, top camera, lean output, stagger.
`--latency-scale` is an explicit sensitivity multiplier. The smoke run
`pcba-sim-smoke-v1` (40 virtual s, 5 requests) verified the loop; it selected no chunk
(3 invalid translations, 1 expired 13.8 s draw).

```bash
uv run sol simulate pcba --profile runs/pcba-loop-latency-tuned-c2-v1 --duration 150 --max-calls 40 --output runs/pcba-sim-new
uv run sol pipeline pcba --layout loop --physics-process --camera-mode top --output-mode lean \
  --schedule stagger --concurrency 2 --transport-tuning --wall-seconds 180 --max-calls 40 --output runs/pcba-loop-tuned-new
```

## Step margin and public top-camera calibration (2026-10-17, second round)

`--output-mode lean2` adds `policies/pcba/pipeline-lean2.txt`: keep every command's
translation norm at most 0.022 m (the validator limit stays 0.025 m and is never
clipped) and reason briefly. `--top-calibration` states the fixed straight-down
overhead camera mapping, computed at runtime from the scene model (640x480:
`world_x = 0.002543*u - 0.8137`, `world_y = 0.5902 - 0.002543*v` at board height;
belt 21.6 px/s). It is public fixed workcell geometry, not object state; the model
still reads every board position from pixels.

| Run | Condition | Valid replies | Median commands/reply | Median request | Reasoning tokens |
|---|---|---:|---:|---:|---:|
| `pcba-latency-attribution-probe-v3` | lean | 8/10 | 10.5 | 9.51 s | 193 |
| same | lean2 | 10/10 | 21 | 9.63 s | 227 |
| same | lean2 + calibration | 10/10 | 20 | 7.28 s | 194 |

Executable commands per inference second: 2.0, 3.1 and 3.5. Paired request latency
for calibration beat lean in only 4/10 snapshots, so the per-request gain is not yet
robust in frozen probes.

Real clock, same 180 s loop setup (top camera 640x480, stagger c2, transport tuning):

| Metric | `pcba-loop-latency-tuned-c2-v1` (lean, 480x360) | `pcba-loop-latency-tuned-c2-v2` (lean2 + calibration) |
|---|---:|---:|
| Mean / median request | 9.10 / 9.13 s | 6.81 / 6.03 s |
| Reasoning tokens (mean) | 229 | 103 |
| Time to first answer delta | 7.20 s | 4.59 s |
| Selected chunks / accepted commands | 9 / 106 | 17 / 240 |
| Wait between chunks (mean) | 20.5 s | 9.5 s |
| Robot motion fraction | 2.9% | 6.7% |
| Invalid replies | 5 | 1 |
| Boards picked / tested / sorted | 1 / 0 / 0 | 2 / 0 / 0 |
| Timing gate | failed (23 ms tick lag) | passed |

In v2 the main discard reason became `start_guard_mismatch` (9): boards released
outside the fixture tolerance and failed regrasps. These are correct public-feedback
rejections; the next limit is placement precision, not transport. One run each; not a
success-rate or stable latency estimate.

## Placement and interception protocols (2026-10-17/18, revised belt)

Still the strict literal-action baseline; the protocols are prompt text the model follows
with its own commands. `--camera-mode adaptive` sends the overhead image and adds the
wrist image (with a runtime-computed public calibration) only from public signals:
vacuum_ok, TCP within 8 cm of the fixture, or TCP low over the pick lane.
`--output-mode lean3` adds `policies/pcba/pipeline-place.txt` (measure the grasp,
hover, settle, correct against the locator pins, seat, release in its own command,
verify; yaw 0 means the USB connector points to +x). `lean4` also adds
`policies/pcba/pipeline-intercept.txt` (read the target's x in the top image, wait
downstream about 2 mm above the board surface with vacuum on, never chase).

Subscription simulations, modeled ultrafast delays, 180 virtual seconds each:

| Protocol | Runs | Picked | Seated / fixture attempts | Tested | Correctly sorted |
|---|---|---:|---:|---:|---:|
| lean3 (placement) | `pcba-sim-belt2-place-c2-ls0/1` | 3 | 3/3 | 3 | 2 |
| lean4 first version | `pcba-sim-belt2-intercept-s*` | 3 | 0/21 (seated at yaw pi) | 0 | 0 |
| lean4 with orientation rule | `pcba-sim-belt2-intercept-v2-s*` | 9 | 6/10 | 6 | 3 |

With interception, the first board is attached at 19-32 s in every run (lean3:
30-113 s). The remaining bottleneck is magazine insertion: ERROR tray 2/2, PASS/FAIL
magazines 1/4; failed boards stopped 12-22 mm short of the slot centre (y=0.21), again
from pushing by tool position without the grasp offset. These are a few development
runs, not success-rate estimates.

## Throughput cycle (2026-10-18)

Goal set by the user: all five boards tested and sorted as early as possible (the
environment keeps five boards). `--output-mode lean5` adds
`policies/pcba/pipeline-cycle.txt`: chain the known steps of a board into a few long
guarded chunks (seat, release, close, test, open, regrasp in one chunk; choose the
output only after the published result), hold before every vacuum or fixture command
because the arm trails full-speed commands by centimetres, and keep the tool yaw from
the fixture regrasp until release. The stagger scheduler also holds a capture while a
committed chunk's test result is not yet public (`awaiting_result`, transport timing
only). `lean6` (`pipeline-cycle2.txt`) is an alternative with two replies per board.

Three simulations each (env/latency seeds 0/0, 0/1, 1/0), modeled ultrafast, 180 s:

| Version | Tested | Correctly sorted | Test to sort (median) |
|---|---|---|---:|
| lean4 interception + placement | 1 / 2 / 3 | 0 / 1 / 2 | 23 s |
| lean5 first version (no hold before release) | 1 / 2 / 4 | 0 / 0 / 0 | - |
| lean5 | 3 / 3 / 4 | 3 / 3 / 4 | 10 s |
| lean6 | 3 / 3 / 4 | 2 / 2 / 4 | 21 s |
| lean6 without wait-only chunks | 3 / 4 / 4 | 3 / 2 / 2 | 17 s |

lean5 is selected for development. No run has yet finished all five boards by 150 s;
about 40 s per board remains: 12-17 s from a sort to the next attachment (fewer boards
left means longer gaps on the loop), 17-21 s from attachment to the test result and
about 10 s to sort. Small samples with large run-to-run variance.

## Model-timed starts and predictive interception (2026-10-19)

`--output-mode lean7` uses `policies/pcba/pipeline-timed.schema.json`, which adds an
optional `start_at_s` (simulation seconds). The executor forwards it literally: the robot
holds until then; a reply selected after its start time is discarded (`late_start`) and a
start beyond the observation TTL is refused. The pipeline context adds public reply
latency p50/p90 and the 0.05 s command period. `policies/pcba/pipeline-timed.txt` asks the
model to predict a board's position at a chosen time from the public belt kinematics,
meet it with the cup already in place, carry it to the fixture without waiting for a
reply, set the tool yaw from the board's USB direction before the catch, and plan the
next catch while sorting.

| Version | Tested | Correctly sorted | Mean time between sorts |
|---|---|---|---:|
| lean5 | 3 / 3 / 4 | 3 / 3 / 4 | 46 s |
| lean7 first version | 1 / 3 / 5 | 1 / 3 / 4 | 41 s |
| lean7 with orientation at catch | 4 / 2 / 4 | 4 / 2 / 3 | 44 s |

No late-start discards occurred, but the model used timed starts in only 1-6 of about
36 chunks per run. In the best lean7 run (`pcba-sim-belt2-timed-v2-s0-ls0`) each board
took about 35 s with 17-24 s of robot motion; the rest was 2-3 short check replies at
the fixture hover and a one-command wait for the test result. Prompt changes alone have
not reached the 20 s per board target.
