# PCBA conveyor, test fixture and magazine cell

Current status, task flow, metrics and the showcase video are summarised in the
[README section](../README.md#pcba-test-cell-belt-to-magazine); the research path is in
[pcba-research.md](pcba-research.md). This page covers setup and evidence boundaries of the
original stopped-line cell; [pcba-loop.md](pcba-loop.md) covers the recirculating belt.

Render a showcase video from any retained run (offline, zero model calls; the scene
dressing is render-only and never reaches policy cameras):

```bash
uv run sol showcase pcba --source runs/RUN --workers 3          # full 1920x1080 video
uv run sol showcase pcba --source runs/RUN --stills 30 70        # preview frames only
uv run sol figures pcba --source runs/RUN --output assets/pcba/steps  # README explainer figures
```

This environment adds a CPU-compatible MuJoCo workcell to sooool. Five free-body
PCBAs arrive on an edge conveyor, stop at a physical end stop and are handled by
an articulated SCARA with an ideal vacuum latch. The task is to load a fixture,
release and clamp the board, request a mocked electrical test, read its eventual
PASS/FAIL/ERROR result, open the fixture and sort the board. PASS/FAIL boards must
be fully inserted and supported by both rails of a vacant magazine slot; ERROR
boards go to the separate amber tray.

## Run without changing the root dependency pins

From the repository root, use the isolated PCBA Python environment:

```bash
.venv-pcba/bin/python scripts/pcba.py demo --output runs/pcba-scripted-new
.venv-pcba/bin/python scripts/pcba.py realtime-smoke --output runs/pcba-clock-new
```

For actual subscription control, select an installed standalone Codex CLI via
`SOL_CODEX_BIN`, signed in with ChatGPT. No paid API fallback is provided:

```bash
export SOL_CODEX_BIN=/absolute/path/to/codex
.venv-pcba/bin/python -m runtime.cli eval pcba \
  --service-tier priority --seed 0 --max-calls 80 --duration 600 --ttl 12 \
  --output runs/pcba-fast-new
.venv-pcba/bin/python -m runtime.cli report pcba \
  --output runs/pcba-fast-new
```

To use the normal root `sol` launcher with the isolated environment, set
`SOL_PCBA_PYTHON=.venv-pcba/bin/python` and run
`uv run sol eval pcba ...` (or `sol report pcba ...`) with the same arguments.
The explicit module commands above use that interpreter directly.

`priority` is Codex Fast. `ultrafast` is an explicit alternative that must be
confirmed by the native thread; the runner fails rather than silently changing
its tier. Current local preflight with Codex 0.163.0 reports priority for Fast,
but null for an ultrafast request. A successfully completed request with an
unconfirmed tier must not be described as Ultrafast evidence. The user selected
Fast after this limitation was reported. See the [official speed documentation](https://learn.chatgpt.com/docs/agent-configuration/speed)
for current Ultrafast plan and workspace requirements.

## What the model receives and controls

The frozen policy is under `policies/pcba`. This is a general GPT-6.1 Sol visual
language model used as a robot policy, not trained VLA robot weights. It receives
three same-time camera snapshots (`overview`, `top`, `wrist`), the task, measured
robot pose/joints/force and vacuum, its commanded robot pose, declared fixture and
conveyor switches, output-slot presence switches, and a public fixed-workcell
calibration. Nominal station coordinates are provided; measured board poses,
future test outcomes, score and evaluator diagnostics are excluded. This is a
calibrated workcell baseline, not pure uncalibrated image-to-action evaluation.

Every request also receives the model's own previous compact memory and the
previous execution receipt. Each request starts an ephemeral model thread with
file/shell/web/connector tools disabled. Prompts, original supplied PNGs, public
model answers, action receipts, token counts and latency are retained. Private
reasoning and account notifications are excluded from the PCBA model event logs.

The model outputs segments of literal XYZ/yaw deltas, a repeat count, optional
vacuum and fixture requests. A repeat applies the same delta every 50 ms. At most
120 commands (6 seconds) can be requested in a chunk; the entire chunk is checked
before execution. The scheduler and inverse kinematics do not choose targets,
recoveries or stopping points. There is no automatic grasp/place/test macro or
oracle motion policy in this evaluation path. The offline scripted demonstrator
remains separate.

The fixed TTL covers camera capture, image preparation, model inference and
chunk execution. Both wall time and simulation time are checked. The model cannot
refresh the trusted timestamp. A rejected/expired command aborts the remaining
chunk, and a new observation is required. Longer TTLs are suitable only for
this stopped-board prototype; they do not demonstrate moving-target control.

## Timing, records and limitations

Physics advances independently at a nominal 200 Hz during inference and action
execution; model waiting does not call `step()` or pause the environment. Software
rendering is CPU-bound. The runner reports wall/simulation drift and late ticks.
Its declared timing check requires maximum tick lag <=20 ms and total drift
<=max(50 ms, 1% of wall time). A failed check remains visible and disqualifies a
1x realtime claim even when handling succeeds.

To reduce interference, the replay recorder saves trusted state snapshots during
the trial, then renders the replay after the live clock stops. The MP4 timeline
uses original wall timestamps and holds the previous sampled camera frame between
samples; it is not a continuous camera capture. `recorded-states.npz` and
`replay.json` preserve the samples and timings. Policy images are rendered live.

Each output directory is exclusive and contains a source hash manifest/snapshot,
scene/assets, per-call public observations and model input/output, exact commands,
fixture events, report, final PNGs and replay. Reports separate attempted and
completed requests, attached boards, completed tests, correct/incorrect sorting,
rejections and full-batch success. A run stopped to change settings remains a
partial run. One successful board or episode is not a success-rate estimate.

Fixture tests are seeded mock events, suction and fixture retention are ideal
welds, magazine pitch is intentionally generous, and small components/tool
geometry are visual only. This prototype does not validate electrical quality,
collision-safe hardware operation, vacuum reliability or industrial cycle time.

## Realtime task pressure

The current conveyor stops and pauses its entire small buffer. There are no
upstream arrivals, expiring boards, required unload windows or downstream
backpressure. Fixture results persist and the robot can hold its pose while a
model thinks. Thus latency mostly reduces throughput; this is a weak realtime
task even though physics runs continuously. The selected Fast trial tested 5/5
boards and sorted 4/5 in a 600 s wall budget, with 5.66 s median model latency.
It supports workflow/handling observations, not moving-target VLA capability or
a repeated-success estimate.

A stronger follow-up should introduce continuous arrivals, a finite input buffer,
parallel fixtures with real release/transfer windows and output backpressure.
Choose feasible rates from measured handling capacity, then evaluate missed
boards, overflow, throughput and fixture utilization as latency changes. A later
conveyor-tracking task can add picking without stopping. Keep the present cell
as the easy baseline; an artificially short command TTL alone does not create
a meaningful production deadline.

## Recirculating conveyor and concurrency extension

Use `sol simulate pcba` for cheaper virtual-clock development before a realtime trial; see [latency tuning and simulation](pcba-concurrency.md#development-simulation-virtual-clock). See [the loop challenge](pcba-loop.md) for moving skewed boards and explicit lap/batch deadlines, and [measured request concurrency](pcba-concurrency.md) for the 1/2/4-request transport benchmark and both clock-failed pipeline diagnostics. The earlier stopped-board run remains a separate baseline.
