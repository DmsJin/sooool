# What GPT controls, and what the program controls

The playing policy is gpt-6.1-sol/low. It chooses movement, shooting, focus,
bombs, and action duration from screenshots. The program executes keys and runs
the original deterministic game rules. No automatic aim, dodge, trajectory
optimizer, or hidden-state controller is part of the playing policy.

The research coordinator can inspect private state offline to diagnose failures
and propose new prompts/configurations. That information is not passed to the
playing model. This iteration changes prompts and control protocols, not model
weights. Each playing request is a fresh turn/thread with explicit inputs.

## Input

* Up to three chronological 640x480 PNG screenshots from the original-asset
  frontend, including player, boss, bullets, and HUD.
* Logical frame numbers for those images.
* Currently held keys and the already-returned action still being executed.
* Controls, action format, game speed, and measured API latency summary.

The model does not receive engine entity coordinates, the random seed, future
bullet scripts, collision forecasts, a computed safe route, or the sampled delay
for its current simulated request. Older images provide visible motion history.

## Output

Example of the current strict single-action schema:

```json
{"player":[224,400],"boss":[270,87],"aim_x":285,"plan":[{"move":3,"shoot":1,"focus":1,"bomb":0,"duration":12}]}
```

`player`, `boss`, and `aim_x` are the model's own screenshot-coordinate estimates,
retained for auditing. `player` may be null when absent/unreliably visible. These
fields never control movement. Only `plan` is parsed into keys; there is no servo
that moves toward `aim_x`.

Current finalist: one action, duration1..48 logical frames. Earlier experiments
also tested up to three actions in one answer. The action conversion itself is
mechanical; it does not repair unsafe or ineffective choices.

| Output | Key conversion |
| --- | --- |
| move0 | No direction |
| move1 / move2 / move3 / move4 | Up / up-right / right / down-right |
| move5 / move6 / move7 / move8 | Down / down-left / left / up-left |
| shoot1 | Hold Z |
| focus1 | Hold Shift |
| bomb1 | Hold X |
| duration12 | Execute for12 logical ticks =0.2 game seconds at60Hz |

The unchanged engine computes movement speed (4.3 normal /2 focused in engine
units per logical frame), diagonal normalization, shot frequency, collision,
damage, death/respawn, bomb effects and cooldowns. A new X press edge triggers a
bomb only when the player/state/resources permit it; holding X across respawn
does not manufacture another press.

At plan end, movement and X release. Z and Shift retain their last values until
another model action changes them. Thus continued shooting comes from a previous
GPT choice to hold Z, not a program that selects targets or firing opportunities.
Original cutins pause logical ticks; action duration follows those logical ticks.

## Arbitration and timing

Single-request experiments apply the returned legal plan. Current race finalist
sends the same prompt/images to four independent Sol requests, with at most eight
requests in flight. Every request is independently recorded and billed. The
first available valid answer for an observation takes effect; later answers for
that observation cannot replace it. Once a newer observation takes effect, older
answers cannot overwrite it. A new effective plan replaces the unfinished suffix
of the earlier plan. Selection uses validity, observation age, and completion
time, never private game state or strategic scoring.

The legacy race finalist can have two unresolved observations in flight. A
separate winner-gated candidate permits a fresh cohort only after the previous
cohort has a valid applied answer (or has exhausted all invalid candidates), while
allowing discarded slow replies to finish. Movement-completion gating is another
explicit configuration, not an automatic dodge controller.

Subscription development waits for actual Sol answers, then applies them only
at simulated completion times drawn from serial API measurements. Independent
race delays are an optimistic hypothesis; shared-delay runs test perfect
correlation. These are not measured concurrent API performance.

Real API verification samples no artificial delays: the browser advances at1x
while requests are outstanding. Capture/apply clocks, actual speed, pauses,
frame gaps, all answers, and all costs are retained. The program alone determines
win/loss: boss HP0 is `won`; merely surviving the60-second limit is not a win.

Optional `early_action_delivery` applies complete streamed JSON only after strict
JSON, schema, and action-limit validation and a durable action record. This does
not predict or complete an unfinished model action. The API request continues to
occupy its capacity slot until terminal validation and usage accounting finish.
Any terminal failure invalidates the episode, including a provisional engine
win. Final success requires `terminal_accounting_complete=true`. This opt-in API
path requires `jsonschema==4.26.0`; the default delivery path is unchanged.
