# Current status

Strict native control remains unsolved. See ../STATE.md for current completed
losses, running24episode batch and exact cumulative budget. Earlier numerical
checkpoints below are historical and superseded where inconsistent.

# Strict GPT actuator research

Only the GPT model chooses speed, steering and duration. Inputs are original legal
front/chase PNGs, whitelisted own/referee telemetry and previously committed model
actuator schedules. The executor validates and delivers commands, skips expired
segments and brakes at expiry. It receives no images or geometry.

## Critical correction

Subscription screening v1/v2/v3 used Codex localImage detail=low. A localhost wire
intercept proved this replaced every image with an omission notice. Those rounds
are INVALID as visual-policy evaluations. Apparent driving failures from those
rounds cannot be attributed to GPT vision or latency. Historical subscription
trials using this same adapter also cannot establish image-based decision making;
older hybrid trials additionally supplied coded numerical CV measurements.

The adapter now uses localImage detail=auto. Two different successive images sent
through the SAME reused filesystem path were captured as input_image; both decoded
payload SHA-256 hashes exactly matched source PNGs. No model/API calls occurred in
this local inspection. Evidence: remote results/native-image-wire-v1 (bad) and
native-image-wire-v2 (fixed).

The supported localImage input is documented in the official OpenAI app-server docs:
https://learn.chatgpt.com/docs/app-server#turns . Actual runtime wire inspection,
not documentation alone, verified this installed version's behavior.

## Current API profile

Model gpt-6.1-sol, low effort, ultrafast, minimal system, auto image detail. Twenty-four
randomly interleaved calls executed STRICTLY SERIALLY without background subscription
jobs. Each stream was fully drained/accounted before the next request. All returned
model/tier identities and all actuator outputs passed checks.

| Images | Actions | Anchor | n | Action available median (s) | Maximum sample (s) |
|---|---|---|---|---|---|
|2|1|arrival|6|1.47777|1.76503|
|3|1|arrival|6|1.21971|1.44141|
|2|3|observation|6|1.70864|2.27991|
|3|3|observation|6|1.74455|2.16380|

Endpoint is complete legal JSON publication, before stream EOF when possible.
Six samples per condition are a screening profile, not a reliable population P95
or evidence that an extra image improves latency. Direct API low-detail profiling
from native-profile-v1 remains valid, but new simulations/final API use auto.

Cumulative conservative session ledger after profiling: $20.72187 of $30;
zero outstanding reservations. Remote research-results/budget.json is authoritative.
Never reset the cumulative ledger or overwrite it with a stale local copy.

## Valid-image experiments

Native screen v4 now compares front/chase cameras, four prompts, single actuator
commands and observation-anchored three-segment plans. Six parallel prefixes with
four real subscription workers each (24 maximum). Simulated arrival times causally
sample the matching auto-image API profile; waiting for slower subscription calls
pauses simulator computation only. No model sees future model answers.

These are 18-second development prefixes, NOT full matches or held-out wins.
No strict native-action win or real-API solve has yet been established.

## Verification and final API path

Four strict boundary tests and ten shared stream/contract tests pass. Offline
actuator audit can rebuild every applied speed/steering from GPT outputs and time
alone. Old invalid-image trials pass this executor audit but remain INVALID for
visual-policy evaluation.

native_action/live.py prepares the real wall-clock HTTP service/meter path with
raw-camera prompts, auto images, streaming legal-JSON publication and the blind
executor. It is compiled but has NOT been live-validated under this strict policy.
Run only after a suitable candidate; retained global budget applies. No pure
pursuit, tracker, CV or adaptive driving code is imported into this driver.

All work lives in the independent research project. roboolympics is an external
read-only environment. No PR, push or upstream delivery is part of this task.

Current checkpoint: all6 valid-image v4 prefixes completed (360 calls), replay
hashes and every exact actuator delivery passed audit. All360 call image hashes
match stored raw PNGs and record auto mode. No strict win yet. Four full 1x
development matches and20 parallel 5x diagnostic prefixes are running. No paid
API requests active; cumulative upper remains20.72187USD.
