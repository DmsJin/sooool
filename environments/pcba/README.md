# PCBA test-cell prototype (MuJoCo)

An original, CPU-compatible scene for **load → seat → clamp → test → unload →
sort**. Four-axis articulated SCARA robot, ideal vacuum tool, five free-body
PCBAs, a stopped edge-belt conveyor, physical fixture bed/guides/clamps, three-slot
PASS / FAIL magazines and a separate HOLD tray. Camera views: `overview`, `top`,
`conveyor_closeup`, `fixture_closeup`, `racks_closeup`, `wrist`.

## Setup and run

Use a separate Python environment; the root workspace has different NumPy pins.
From the repository root:

```bash
uv venv --python 3.11 .venv-pcba
uv pip install --python .venv-pcba/bin/python -r environments/pcba/requirements.txt
.venv-pcba/bin/python scripts/pcba.py demo --output runs/pcba-demo-new
.venv-pcba/bin/python scripts/pcba.py realtime-smoke --output runs/pcba-clock-new
.venv-pcba/bin/python -m unittest discover -s tests -p test_pcba_environment.py
```

The entrypoint selects Mesa EGL software rendering by default, with two llvmpipe
threads. Set graphics variables before running to choose another renderer.
On a desktop with a display, use `MUJOCO_GL=glfw ... scripts/pcba.py view`.
The scripted demo needs no server, model request, API credential or external robot CAD.
For actual subscription control and reports, see [the PCBA integration guide](../../docs/pcba.md).

## Policy interface

Add `environments/pcba` to Python's import path, then import `PCBATestCell` and
`RealtimeSession` from `pcba_gym`. This is an explicit Python adapter, not yet a
registered Gymnasium environment or an installed `sol` CLI subcommand.

- `reset(seed)` returns public observations, with deterministic board jitter and
  private, seeded mock test outcomes. Every demo includes two PASS, two FAIL and one ERROR in a private permutation.
- `observe(cameras=(...), width=640, height=480)` returns same-time RGB arrays,
  capture time, task, robot proprioception, vacuum signal, tool force, fixture
  switches, tester state, released result, conveyor running/pickup-ready switches,
  declared output-slot occupancy switches and last command receipt.
- `command(action, observed_at_s=..., ttl_s=.5)` submits a bounded action. Use the
  capture time assigned by the trusted observation producer; do not let a policy
  invent a fresh capture time. Stale/future observations are rejected.
- Action fields: `delta_xyz_m` (scene-world frame, max norm 0.025 m),
  `delta_yaw_rad` (max 0.2 rad), `vacuum` (bool), and optional `fixture`
  (`close`, `open`, `start_test`). The mechanically fixed inverse kinematics
  and position servos execute the requested target; they do not select goals.
- `step(action)` advances one 50 ms **offline development** interval. It returns
  `(observation, reward, terminated, truncated, info)`. This call does not render
  images by default. Call `observe(cameras=...)` explicitly.
- `RealtimeSession(env).start()` owns a separate 200 Hz physics thread. During
  realtime execution use `command()` and `observe()`, never `step()` or reset.
  Render from a separate state snapshot, outside the physics lock. Late ticks,
  wall/simulation time and drift must be checked; no accelerated catch-up hides
  late physics. This is soft realtime, not a hardware realtime guarantee.
- `diagnostics()` is evaluator-only: exact board poses, scoring, receipts,
  dropped boards and event history. Never pass it to the online actor.

Robot joint order is shoulder radians, elbow radians, Z-slide metres, wrist-yaw
radians. TCP positions are measured world coordinates. Device presence/vacuum
signals are declared virtual sensors. PASS/FAIL/ERROR belongs to a board/test ID
and is revealed only after test completion; a FAIL or ERROR correctly sorted is
successful robot handling. Success requires a released, upright, settled board
fully inserted in an empty slot, supported by both slot rails in the correct
magazine (or on the HOLD tray base). Proximity to the mouth alone is insufficient.
Fixture start/open requests are gated
against absent boards, incomplete clamping and a running tester.

## Evidence and fidelity boundaries

`demo` uses **evaluator board poses** to issue ordinary bounded robot actions. It
is an oracle/scripted environment smoke, with zero model calls, not a VLA score.
It produces native MuJoCo PNGs, scene XML, generated texture assets, event log and
report. Failed output directories are retained. `realtime-smoke` separately
checks that the physical clock advances while a policy waits and rejects a stale
reply. The offline demo must not be presented as realtime VLA validation.

All geometry/textures are authored procedurally here; the robot is a simplified
SCARA, not a manufacturer-validated CAD model. Board substrate, fixture, table
conveyor, magazine and tray contacts run in MuJoCo. Small components are visual geometry. Suction
uses a proximity-gated ideal weld; fixture retention uses a gated ideal weld.
The conveyor motor is idealized as a bounded tangential force applied only to
boards touching the edge belts; board positions are never animated or teleported
by the transport. Its physical end stop arrests the first board, and a declared
presence switch pauses the motor until pickup. This is a small batch buffer,
without upstream arrivals or SMEMA signaling. Magazine slots are horizontal,
open toward -Y, loaded from the bottom up; 80 mm pitch intentionally provides
clearance for the simplified tool. They represent a sparse demonstration rack,
not a dimensionally accurate dense production magazine. The scripted demonstrator
approaches from the front, inserts with 6 mm nominal vertical clearance, releases
onto the rails and withdraws before raising. Small tool geometry is visual only;
there is no validated tool-to-rack collision envelope.

There is no vacuum pressure/leak model, PCB flexure, detailed probe contact,
connector mating or calibrated force sensing. Electrical results are seeded
**mock device events**, not SPICE or real electrical measurements. Test control
and quality rules are fixed. The separate `runner.py` connects the frozen visual-action baseline through the
existing native Codex subscription transport; it never uses evaluator poses.
This is a general vision-language model controlling literal robot actions, not
a trained robot VLA checkpoint.

Next useful extensions: trained VLA policy adapters, richer observation history,
force/placement fault cases,
multi-fixture timing, and demonstrator data. Keep these separate from the current
scene and clock checks.

The optional [recirculating conveyor](../../docs/pcba-loop.md) is available through `scripts/pcba.py loop-demo` or `scripts/pcba.py pipeline --layout loop`. [Concurrency measurements](../../docs/pcba-concurrency.md) distinguish throughput from latency and reject clock-failed trials as realtime evidence.
