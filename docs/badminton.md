# Badminton: conditional goals over continuous camera execution

[Watch the 15-second opening serve and rally](../assets/gameplay/badminton.mp4).
The source match completed 8:11 with 90/97 legal returns, at seed 101 and L1/S3.
See the [completed-match evidence](../artifacts/badminton/README.md) for its source
snapshot, protocol, API accounting and native replay audit.

## Actual realtime API run

Use the same Python/GPU setup below. `sol eval badminton` runs one native match
with `gpt-6.1-sol / low / ultrafast`, one request in flight, and actual API
response timing. The game advances at S3: 100 Hz native physics and 33.333 control
steps per wall second. Historical profile statistics remain prompt context;
they do not schedule response delivery.

```bash
uv run sol preflight badminton --duration 10 --output outputs/badminton/preflight
uv run sol eval badminton --budget-usd 15 --ledger outputs/badminton/budget.json --env-file /absolute/path/to/.env \
  --output outputs/badminton/api-101
uv run sol audit badminton --output outputs/badminton/api-101
uv run sol report badminton --episodes outputs/badminton/api-101 \
  --output outputs/badminton/api-101
```

The equivalent console commands are `sol preflight badminton`, `sol eval badminton`,
`sol audit badminton`, and `sol report badminton`. Preflight makes zero API calls.
API credentials come from the explicitly selected env file or `OPENAI_API_KEY`;
they are not retained. An external pinned source snapshot without Git metadata
requires `--environment-revision da1f787f775ea6524d698c0b063157ded4c0fef9`.
The manifest distinguishes a declared snapshot revision from a Git checkout.

The selected `tactical-goal-v2` recipe uses the joint contact/launch solver migrated
from `badminton_sol_target_api20_gpu_001`. SOL returns `normal`, `under_pressure`,
`opponent_back`, `recovery`, `horizon_game_s`, and `memory`. Each branch supplies
one side/shot goal. The controller selects a branch from public observations.
It searches the remaining contact trajectory, including earlier high contacts.
It uses a legal approximation to that same goal when exact placement is unavailable.
Exact plans, projected plans and rule fallbacks remain separate from actual outcomes.
A committed swing retains its goal through camera and delivery corrections.
Requests start during serving and receiving preparation, and refresh before expiry. The 1–10 game-second horizon starts
at the source observation, so thinking time consumes it. Expired replies are discarded.

The realtime recipe retains tactical placement and recovery. Its output adds
`brief`: one English public decision summary, at most 60 characters, from the
same response as the intent. Complete legal JSON becomes available before
terminal usage settlement. A new request waits for the previous terminal event.
Point boundaries clear the active intent and discard previous-point replies.
Factual memory persists across points.

Rendering/control and native stroke planning run in separate processes. Native
planning requests a 0.4-wall-second lead, rounded up to 14 control steps at S3
(0.42 wall seconds). Absolute contact
times survive capture and preparation delay. A missed planning deadline is
recorded and dropped; it cannot trigger synchronous replanning in the physics
loop. Subscription simulation uses the same lead and command scheduler, and injects
measured native planning time into its virtual clock.
Commands produced while the planner is busy remain in a FIFO queue. Submission
keeps each command's absolute contact time and subtracts the time spent waiting.
Point boundaries discard queued commands explicitly. A busy planner does not
silently discard a stroke already committed by the camera controller. A camera proposal
becomes active only after installation acknowledgement. Up to three contact/stance
candidates run in parallel robot-only rehearsals. Candidates must deliver position
within 2 cm, face within 3 degrees, avoid robot stops, and predict a legal outgoing
flight using rehearsed velocity. Geometry corrections retain the goal and pass the
same checks before replacing the active stroke.

The default endpoint is the native match: first to 11 by two points, capped at
15, including the environment's original hit/point safety caps. Limits are 300
game seconds, 900 running wall seconds, 300 requests and the explicit dollar
budget. A limit stop remains incomplete. All requests drain for usage settlement
after gameplay ends. Run time excludes startup and post-game settlement.

Acceptance also requires P99 scheduling lag at most 20 ms, maximum lag at most
100 ms, and complete terminal accounting. Native wins/losses, timing validity,
replay validity and completion are reported separately. The report retains API
JSON readiness, terminal latency, capture-to-intent latency, cache/token usage
and total billed cost. There is no token-count preflight request.

After native replay verification, the report generates `realtime-s3.mp4` and
`index.html`. The video renders every recorded control step at 100/3 FPS, preserving
the S3 wall duration. Replay and video timing use each run's retained slowdown,
including earlier S2 runs. It shows both native cameras and an English decision panel.
Intent acceptance and applied racket plans have separate display states. This
is a verified replay of actual API controls, not a recording of simulated delays.

## Subscription simulation

Simulation uses the same `tactical-goal-v2` execution layer. Fixed tactics and SOL
both use camera interception, joint contact/launch search and delivery correction.
New replies affect uncommitted strokes. The original reference owns native serving
and recovery mechanics. These are hybrid tactical goals; SOL does not emit joint actions.

The `tactical-v1` policy files and historical result artifacts retain the earlier
`source_tactical_005` protocol. They are not the selected recipe.

## Setup

Use a separate Python 3.11 environment matching the original checkpoint runtime.
The launcher prepares its independent dependencies. Keep the external
RoboOlympics environment read-only. A working NVIDIA EGL driver is required.

```bash
uv run sol env setup badminton
export SOL_CODEX_BIN=/absolute/path/to/codex
export SOL_CODEX_HOME=/absolute/path/to/existing/chatgpt-login
export MUJOCO_EGL_DEVICE_ID=0
```

The [environment manager](environments.md) selects Python 3.11, the pinned source
and thread limits. The launcher selects `MUJOCO_GL=egl` and `PYOPENGL_PLATFORM=egl` before importing
MuJoCo. `MUJOCO_EGL_DEVICE_ID` selects the GPU. The reference runtime used Python
3.11.17, MuJoCo 3.3.7, NumPy 2.2.6 and Pillow 11.3.0.
The tested Codex CLI is 0.162.1. Authentication remains outside this repository.

## Run and audit

```bash
# Rule-only smoke and native replay: zero model calls.
uv run sol simulate badminton --source rules --duration 10 --output runs/badminton/smoke
uv run sol audit badminton --output runs/badminton/smoke

# Paired development windows, using the same seed and policy implementation.
uv run sol simulate badminton --source rules --seed 101 --duration 60 --output runs/badminton/rules-101
uv run sol audit badminton --output runs/badminton/rules-101
uv run sol simulate badminton --source sol --seed 101 --duration 60 --output runs/badminton/sol-profile-101
uv run sol audit badminton --output runs/badminton/sol-profile-101
uv run sol report badminton --episodes runs/badminton/rules-101 runs/badminton/sol-profile-101 --output runs/badminton
```

The same commands are available as `sol simulate badminton`, `sol audit badminton`,
and `sol report badminton`. The launcher selects the prepared Python environment.
The default recipe uses online SOL with profiling context. Each output directory must be new. A `STOP` file in
its parent interrupts the episode and preserves partial evidence.

## Clocks and model inputs

The simulation protocol is L1/S3, native 100 Hz physics, and public observations at up
to 10 Hz game time. One modeled wall second corresponds to 33.333 physics steps.
Rendering, perception, local decision work, and image serialization incur measured
virtual delay. Native mechanical planning consumes measured virtual time and uses
the same 14-step installation deadline as realtime. Contacts keep their absolute game times.

Requests are serial, at most once per game second and 300 per match. SOL receives
the original public two-camera/four-frame image sheet, filtered public state and
specification, accepted history, memory, and optional profile statistics. Seeds,
internal installation acknowledgements, simulator truth, future delay draws,
pending answers and offline audit data never
enter its prompt.

Subscription simulation explicitly requests **default tier with Fast disabled**.
Native configuration must report default tier and Fast false. Codex 0.162.1
reports the default thread tier as `null`; accelerated tier echoes are rejected.
These values are checked and recorded. The minimal game system instructions
replace coding instructions. Project documents, skills,
tools and memory sources are disabled. The existing signed-in ChatGPT subscription
supplies all new model decisions. There is no paid API fallback.

Virtual scheduling uses the retained 10-call **API Ultrafast** conditional-strategy
profile in `profiles/badminton/conditional-api-10.json`. It records complete valid
JSON readiness and terminal service time through the live API transport.
The earlier API20 measurement remains historical evidence.
The same profile summary is prompt context in realtime runs; realtime delivery
uses actual API readiness without sampled delays. Actual subscription compute time is recorded separately.
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
Raw logs and videos belong in ignored `outputs/` or `runs/`; compact published
validation evidence belongs in `artifacts/badminton/`.

## Reception diagnosis and profiling

`sol diagnose badminton --episodes ORIGINAL_RUN --output NEW_DIRECTORY` restores
each settled audited stroke's verified physical prefix and frozen public goal. This is
an offline counterfactual, with zero model calls. Native snapshots remain outside
the policy input. Original evidence is retained. The comparison reports legal
returns and preserved returns separately. `complete` requires an outcome for every
source case, valid clocks and zero invalid commands. It does not impose a fixed
case count or a policy-promotion threshold.

`sol profile badminton --episodes ORIGINAL_RUN --budget-usd 15 --ledger outputs/badminton/budget.json --output NEW_PROFILE`
measures exactly 10 distinct public camera observations through the realtime API
transport. Use the same `--ledger` and dollar cap for later evaluations, and pass
`--profile NEW_PROFILE/profile.json` to select the measurement. Historical API20
evidence remains separately labeled. `sol eval badminton --source rules` runs the
fixed tactical control with zero model calls and the same native match endpoint.

## Goal audit and source ownership

The implementation lives in `environments/badminton`, and the goal policy contract
lives in `policies/badminton/tactical-goal-v2`. It has no dependency on the parent
latency-sensitive-bench experiment package. `test_goals.py` retains the public-camera
regressions that exercise goal adoption and committed-goal delivery correction.

Realtime audit counts each incoming flight once. It separates planned exact goals,
legal projections and rule fallbacks from actual hits and legal returns. Actual goal
placement uses the measured post-hit launch and the public flight model to estimate
landing without opponent interception. It is not an observed landing for every shot.
A planned exact goal does not itself establish successful delivery.
