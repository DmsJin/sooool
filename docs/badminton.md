# Badminton: delayed tactical preferences over continuous reference execution

The selected `tactical-v1` policy is the working `source_tactical_005` checkpoint.
SOL returns `side`, `shot`, `recovery`, and `memory`. The original camera-only
reference continuously serves, tracks the shuttle, chooses contact times, moves
the base, commands the racket, and corrects mechanical execution.

`side` selects left, center, or right. `shot` selects clear, drop, or smash.
`recovery` supplies a waiting base coordinate within the public range. New
preferences apply when a new rally stroke is planned. They do not restart a
committed swing. An infeasible preferred shot retains the reference's shot.
Preferences and memory reset at point boundaries. Delayed previous-point replies
are discarded. These are hybrid tactical decisions, not direct SOL racket control.

## Setup

Use a separate Python 3.11 environment matching the original checkpoint runtime.
The root workspace pins another NumPy version. Keep the external RoboOlympics
environment read-only. A working NVIDIA EGL driver is required.

```bash
git clone https://github.com/CHIGUI0/roboolympics /tmp/badminton-environment
git -C /tmp/badminton-environment checkout da1f787f775ea6524d698c0b063157ded4c0fef9
python3.11 -m venv /tmp/sol-badminton-venv
/tmp/sol-badminton-venv/bin/pip install -r environments/badminton/requirements.txt
/tmp/sol-badminton-venv/bin/pip install --no-deps -e .
export BADMINTON_ENV_ROOT=/tmp/badminton-environment
export SOL_CODEX_BIN=/absolute/path/to/codex
export SOL_CODEX_HOME=/absolute/path/to/existing/chatgpt-login
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export MUJOCO_EGL_DEVICE_ID=0
```

The launcher selects `MUJOCO_GL=egl` and `PYOPENGL_PLATFORM=egl` before importing
MuJoCo. `MUJOCO_EGL_DEVICE_ID` selects the GPU. The reference runtime used Python
3.11.17, MuJoCo 3.3.7, NumPy 2.2.6 and Pillow 11.3.0.
The tested Codex CLI is 0.162.1. Authentication remains outside this repository.

## Run and audit

```bash
PYTHON=/tmp/sol-badminton-venv/bin/python

# Rule-only smoke and native replay: zero model calls.
$PYTHON scripts/badminton.py simulate --source rules --duration 10 --output runs/badminton/smoke
$PYTHON scripts/badminton.py audit --output runs/badminton/smoke

# Paired development windows, using the same seed and policy implementation.
$PYTHON scripts/badminton.py simulate --source rules --seed 101 --duration 60 --output runs/badminton/rules-101
$PYTHON scripts/badminton.py audit --output runs/badminton/rules-101
$PYTHON scripts/badminton.py simulate --source sol --seed 101 --duration 60 --output runs/badminton/sol-profile-101
$PYTHON scripts/badminton.py audit --output runs/badminton/sol-profile-101
$PYTHON scripts/badminton.py report --episodes runs/badminton/rules-101 runs/badminton/sol-profile-101 --output runs/badminton
```

The same commands are available as `sol simulate badminton`, `sol audit badminton`,
and `sol report badminton` when the selected Python environment provides `sol`.
`--profile-info hide` hides only profiling statistics. `--source sol-frozen`
retains the first accepted intention per point. The default recipe uses online
SOL with the profile shown. Each output directory must be new. A `STOP` file in
its parent interrupts the episode and preserves partial evidence.

## Clocks and model inputs

The fixed protocol is L1/S2, native 100 Hz physics, and public observations at up
to 10 Hz game time. One measured wall second corresponds to 50 physics steps.
Rendering, perception, local decision work, and image serialization incur measured
virtual delay. Native mechanical planning time is recorded but is not injected,
as in the original checkpoint. Contacts keep their absolute game times.

Requests are serial, at most once per game second and 64 per window. SOL receives
the original public two-camera/four-frame image sheet, filtered public state and
specification, accepted history, memory, and optional profile statistics. Seeds,
simulator truth, future delay draws, pending answers and offline audit data never
enter its prompt.

Subscription simulation explicitly requests **default tier with Fast disabled**.
Native configuration must report default tier and Fast false. Codex 0.162.1
reports the default thread tier as `null`; accelerated tier echoes are rejected.
These values are checked and recorded. The minimal game system instructions
replace coding instructions. Project documents, skills,
tools and memory sources are disabled. The existing signed-in ChatGPT subscription
supplies all new model decisions. There is no paid API fallback.

Virtual scheduling uses the retained 100-call **API Ultrafast** tactical profile.
It measured request-send through response termination, excluding token preflight
and local accounting. Actual subscription compute time is recorded separately.
If it exceeds a virtual delivery deadline, simulation waits for the answer.
This mode is not continuously advancing real-time API evaluation.

## Evidence and acceptance

The historical experiment used seeds 101/111/121, each for 60 game seconds.
Aggregate scores were rules 10:8, SOL with profile 4:17, SOL without profile 4:12,
and SOL frozen per point 3:13. These development windows established legal
returns. They did not establish a full-match win rate or a SOL/profiling advantage.

`run.json` and `manifest.json` identify the resolved recipe, source revision,
external environment, GPU renderer, seed and clock conditions. `events.jsonl`
records observations, decisions and actions. `audit.json` verifies public states,
native execution feedback, point boundaries, scores and termination before
extracting offline diagnostic outcomes and ball trajectories. Replays request no
model answers. Original and newly generated model decisions remain separate.

The report exports 1x game-time videos at 10 FPS from held public observations.
New GPU runs retain their own measured preprocessing times and observed scores.
Raw logs and videos belong in ignored `runs/`; compact validation evidence belongs
in `artifacts/badminton/`. No new profiling calls are required for this port.
