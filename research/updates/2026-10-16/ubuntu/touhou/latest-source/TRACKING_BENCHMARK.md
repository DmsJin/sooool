> **Retained source-harness research record.** This report/protocol describes its original experiment stage. “Current”, “ongoing”, “selected” and acceptance statements below belong to that stage; use the [selected Touhou learning record](../../../../../../docs/touhou-research-record.md) for the released policy, actual API wins and current launcher status. The original report follows unchanged.

# Frozen private tracking benchmark v1

Purpose: select prompts for useful sustained firing under real control latency;
this is development scoring, not weight training, an online servo, or proof of
held-out win rate. Original engine/difficulty, controller action schema and model
input boundaries remain unchanged. No benchmark score or future state goes into a
live actor request. Policy selection can use aggregate results after an offline
batch ends.

Use the already inspected successful API episode's **video/visual seconds 17–28**
for development cases, alongside left/right turns, already aligned cases, threat
cases and matched human prefixes. Do not call this episode held out. Preserve
original screenshot hashes and source capture IDs. Answers must be collected
from exactly those historical images and permitted control/delay metadata, with
no future screenshot, human input, seed-based trajectory or precise state.

## Fixed replay and scoring

Replay each source's complete actual action log and verify its final state before
scoring. Restore the exact actual prefix through the observation's capture time;
retain its known remaining/pending chunks during the delay. Suppress every future
source decision. Delay assumptions are **2.69135 and 3.170205 seconds**, the measured
capture-to-apply P50/P95 from the successful early-delivery API run. They are
assumptions for counterfactuals, not new measurements or a latency tail guarantee.
Convert seconds into ceil(seconds × 60) visual frames; cutins consume visual time
but produce no logical scoring ticks. Execute the completed model plan, then
score exactly **180 logical ticks**, or until terminal status. Z/Shift persist and
movement/X expire according to the original executor.

Freeze this ranking before results:

1. Apply a safety/resource gate first: a candidate claiming improvement must not
   increase aggregate post-action hits, reduce final win count in full episodes,
   or spend more bombs than the baseline on the same cases/delays. Show all these
   quantities separately; avoid trading lives for an unnamed scalar reward.
   Also require no increase in alive nonshooting ticks, so releasing Z cannot
   manufacture a better miss-run tie-break. Bomb use is gross `bomb` events;
   net inventory changes and any bomb gains are independent diagnostics.
2. Among eligible candidates, prefer higher mean **full 180-tick shot-only damage**,
   with equal weighting per case, delay and repeat. Tracking reward normalizes
   that damage by 360 HP, the ideal 120 DPS for three seconds; fixed denominator
   prevents an early death shortening the denominator. This includes in-flight
   prefix shots, which are identical across candidates for each matched state.
3. Tie-break by lower full-window longest eligible no-hit run, then higher shot
   damage in ticks 61–180. The latter excludes pre-action projectile travel
   (maximum original projectile crossing time is under 60 ticks) but is secondary
   so prompt recovery during the first second is not discarded. Report individual
   cases and variance, not just the mean or a best repeat.

The primary damage excludes bombs exactly: original orb impacts are explicit
`orb_hit` events, each dealing 30 HP and adding 60 score. Shot hits deal 5 HP/add
10 score; graze adds 25 score. At each original-engine tick infer
`shot_hits = (score_delta − 25×graze_delta − 60×orb_hit_count)/10` and fail on any
unaccounted/nonintegral result. Do **not** subtract 240 per bomb press: impacts can
occur outside the scored window or never occur. Report nominal shot damage,
actual HP loss (clamped to zero at victory), actual orb impact damage and bomb
press count separately. Terminal overkill can make nominal damage slightly
exceed HP loss; it is identified as nominal rather than hidden.

A miss run consists of consecutive logical ticks while alive, Z held and no shot
hit. A normal paired-shot cadence therefore contains short four-tick gaps. Dead
or nonshooting ticks break a miss run and are independently counted; they cannot
be presented as improved tracking. Cinematic pauses are not inserted into the
logical trace. Instantaneous horizontal alignment/error and moving away from
current boss position are **diagnostics only**: future projectile travel and
safe evasion can make them misleading. `stale_position_chase_ticks` counts
movement toward the observed old boss side but away from its current side;
exclude respawn teleports. Do not turn these diagnostics into an automatic target.

Human actual future controls can serve a separately labeled **undelayed human
reference**, not the unique correct action and not an equally delayed baseline.
Human matched-prefix Sol evaluations use the same delayed protocol above.

## Commands

Run from the research worktree. No model calls are made by this evaluator:

```sh
python -m research.tracking_benchmark --url http://127.0.0.1:8796/game/ \
  --output /tmp/tracking-actual.json episode /path/to/actual-api-episode \
  --window 17 20 --window 20 28 --window 17 28

python -m research.tracking_benchmark --url http://127.0.0.1:8796/game/ \
  --output /tmp/tracking-cases.json cases --dataset /path/to/dataset \
  --comparison /path/to/completed-visual-comparison --source-root /path/to/local-source-mirror

python -m research.tracking_benchmark --url http://127.0.0.1:8796/game/ \
  --output /tmp/tracking-human.json cases --dataset /path/to/human-dataset \
  --comparison /path/to/completed-human-comparison --human-source /path/to/verified-human-recording
```

Episode reports replay actual source actions, including future decisions, solely
for retrospective diagnostics. Case reports replace future actions after the
capture boundary and are counterfactuals. Keep both report types separate.

For full episodes compare win status/time, shot-only DPS, long misses, hits and
bombs, with identical frozen seeds/config. A long episode's reward uses its actual
logical span rather than a 180-tick denominator. Do not promote based solely on
case scores: verify a promising frozen prompt first in subscription latency
simulation, then within the remaining paid budget in uninterrupted API realtime.

## Frozen batch summary

```sh
python -m research.tracking_summary /tmp/tracking-cases-v1.json \
  --output /tmp/tracking-selection-v1.json --baseline tracking_dodge_adaptive \
  --expected-rows 144
```

The summarizer requires a complete verified source report, exactly the frozen
row count, both frozen delays, no duplicate pair and identical Cartesian
case/repeat/delay coverage for every candidate. It pairs each candidate against
the baseline on those exact keys, reports case and delay breakdowns and applies
the previously frozen ranking without changing weights. Aggregate gross bombs,
hits, deaths and alive nonshooting ticks must each not increase. Exact ranking
ties retain the baseline. A selected case candidate is eligible for **episode
testing**, not declared a realtime improvement; full-episode win and safety
gates still have to be checked separately.

### Motion diagnostic windows

`full_window_moving_ticks`, `full_window_moving_away_from_current_boss_ticks` and
`full_window_stale_position_chase_ticks` cover all 180 post-action logical ticks.
Use these fields for short actions: the original single chunk expires by 48
ticks, before the secondary steady window begins at tick 61. `steady_*` fields
cover only the steady window; old unprefixed motion fields are retained aliases
for that steady window and must not be described as full-window motion. Respawn
teleports are excluded in both windows. These diagnostics do not enter reward,
ranking or safety gates: moving away from the boss's current position can be a
correct interception or evasion. This clarification changes no frozen selection
metric or weight. The observed private boss x is recorded solely for offline
diagnostic reproducibility and never becomes actor input.
