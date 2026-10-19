# Recirculating PCBA test-and-sort challenge

The current loop uses explicit 100 Hz native physics and the same 20 Hz robot
command cadence. The stopped-line baseline and earlier loop oracle development
clips used 200 Hz. Process-isolated physics is available with `--physics-process`;
rendering and inference run outside that process. Neither catch-up bursts nor
pausing for model replies are used. Six local preflight attempts are retained:
the first four failed clock drift, the fifth passed timing but exposed a setup
instability, and the sixth passed timing with zero physics warnings after fixing
initial board placement.

This variant retains the fixture and PASS/FAIL magazines plus ERROR tray. Its
input is a physical racetrack belt, with two straight runs and two semicircular
turns. Five free-body PCBs circulate continuously. Missed boards return physically;
there is no end stop, global inference pause or position reset on each lap.

Initial lateral offsets are seeded within +/-21 mm and yaw within +/-0.60 rad.
Turn/edge contact can further change orientation. A conveyor surface model (see Belt model revision below)
approximates a guided modular belt. No yaw motor
automatically aligns the boards. This is an ideal belt-drive approximation, not
a validated factory friction model. Suction remains a proximity-gated ideal weld;
electrical test outcomes are mock device events revealed only when testing ends.

The nominal path length is 1.851 m, target speed 0.055 m/s and nominal lap time
33.65 s. Actual free-board progress depends on slip, lane offsets and contacts.
The right straight has a marked 0.28 m pick window, nominally 5.09 s of passage.
The task has a 150 simulation-second batch deadline and at most four full
unpicked laps per board. These configurable-code prototype constants are challenge
settings, not production throughput requirements. Expiry is latched and cannot
be undone by sorting late. Object-wise lap and deadline records are evaluator-only.

The robot must locate the board, predict a reachable interception, grasp while
moving, preserve the attachment's relative yaw, then correct the board to the
fixture's 4 mm position / 0.10 rad yaw tolerance. After a published electrical
result, it unloads and sorts into a vacant matching output slot. Full completion
requires every board correctly sorted on time; successful late sorting is a
different outcome. Camera poses, fixed path calibration, robot proprioception,
belt target speed and declared switches are public. Exact dynamic board poses,
velocities, evaluator lap records and latent test results are not model inputs.

```bash
export SOL_PCBA_PYTHON=.venv-pcba/bin/python
uv run sol loop-demo pcba --output runs/pcba-loop-oracle-new
uv run sol pipeline pcba --layout loop --physics-process --concurrency 1 --duration 150 --max-calls 24 --output runs/pcba-loop-model-new
# Offline video export from already-recorded native states; zero new model calls.
$SOL_PCBA_PYTHON scripts/pcba.py export --source runs/pcba-loop-oracle-new
```

`loop-demo` is explicitly an offline oracle validation: with `--unattended-seconds 45`, it deliberately lets the
boards circulate unattended first; it uses private poses/velocity and robot
feedback for scripted interception, alignment, testing and sorting. Its results
are never a VLA score or realtime-clock claim. `pipeline --layout loop` uses only
the declared actor interface, with every literal action chosen by the model. The
model runner includes no hidden tracking controller or grasp macro. No actual
model success on the new loop is established by the environment demonstration.

The [concurrency measurements](pcba-concurrency.md) show why prediction matters:
current Fast inference takes roughly 5–6 s, already comparable to one full pick
window. Prediction should cover capture age, inference, queued/executing motion,
and approach time through actual contact. Large concurrency produces more
candidate answers, but increases stale branches and does not guarantee lower
latency. A future explicit hybrid experiment can give a VLA short-horizon goals
and a separately evaluated vision servo; it must be labeled differently from
the current literal-action baseline.

`--continue-after-deadline` is an explicitly labeled diagnostic option: deadlines
remain failed, but the run can continue to measure whether all boards eventually
finish. It cannot turn a late completion into a successful challenge episode.

## Single camera comparison

`pipeline --layout loop --camera-mode top` supplies only the fixed 640x480
overhead image to the model. Robot proprioception, public fixture switches and
output occupancy remain available. The default `--camera-mode multi` retains
overview/top/wrist. Camera ordering in the policy prompt is updated to match the
actual input. Final replay cameras are evaluator-only and do not become policy
inputs. No detector, tracker, grasp macro or prediction controller is added by
this option. It can be compared with the first 150 seconds of the retained
four-worker, three-camera trial without changing the literal action interface.

Badminton's model receives one 1920x720 image sheet containing multiple camera
views/history; its local controller separately detects the shuttle from pixels,
fits/predicts flight and corrects contact while the model chooses conditional
shot/placement goals. One encoded image is not equivalent to one physical camera.
PCBA's mostly planar belt geometry makes a single overhead camera plausible, but
camera reduction alone does not provide that continuous visual control layer.

## Belt model revision (2026-10-17)

Earlier loop runs used force-driven free boards on 100 coplanar box segments. A thin slab
could catch the next segment's end face and stop for seconds to the whole run, while the
belt kept running; later boards then rear-ended it and could ride over or flip. With no
robot motion at all, seeds 0-2 showed stalls of 6-73 s and one numerical instability
(e.g. seed 0, board 2 stuck at y=-0.089 from 34 s for 6 s, the same stall that left the
robot waiting in `pcba-sim-ultrafast-modeled-c2-ls0`).

The revised belt is a conveyor surface model:
- Segments pitch up 0.03 rad along travel (sawtooth), so each entry edge sits below the
  board while the exit edges carry it at the unchanged 0.800 m top.
- A board within the belt footprint at belt height (not held, clamped or sorted) takes
  the belt's surface velocity directly: 0.055 m/s along the path, scaled by radius on the
  curves, turning with the belt counter-clockwise. Its height and level are held to the
  belt surface. Its random lane offset and skew are kept; yaw is never servoed.
- Each board follows its own point on a virtual rigid belt, so spacing stays constant; a
  blocked board lags at most 10 mm and never surges forward when released.
- Contacts with the robot, fixture, outputs and other boards remain physical.

Belt-only validation, 10 seeds x 150 s, no robot motion: no stall over 1 s, every board
8.27-8.28 m travelled (nominal 8.25 m, four laps), closest board spacing 0.28-0.32 m,
maximum tilt 1.4 deg except one 6.3 deg transient, no drops or physics warnings. The
scripted oracle (`runs/pcba-loop-oracle-belt-v1`, not model evidence) sorted 5/5 boards
correctly with one lap deadline missed, like the earlier `pcba-loop-oracle-v8`.

Runs before this revision used the earlier belt; their results are not comparable with
later runs on the revised belt.
