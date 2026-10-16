# Frozen V2 tracking hypotheses

Frozen before the second collection. Use the same 12 public cases, two repeats, original images/memories, observed delay summaries and unchanged baseline `tracking_dodge_adaptive`. New candidates are `tracking_dodge_safe_intercept_v2` and `tracking_dodge_safe_corridor_v2`. Both append fewer than 1,300 characters to the original baseline instead of the long V1 exposition. No engine/executor/controls/action contract changes. All existing strategies, including V1, remain byte identical.

## V1 evidence motivating the changes

The 144 counterfactual windows in `/tmp/touhou-tracking-study-v1/selection-v1.json` retained baseline: intercept improved mean shot damage 5.8% but increased hits from 2 to 4; turn guard improved damage 11.4% but increased hits to 6. Neither passed the predeclared safety gate. These are retrospective development windows, not episode success rates.

Three failure types explain the safety regression:

- In one visual observation near the bottom of a bead ring, both V1 candidates commit right without a bomb. At the slow latency stratum, collision follows only three logical ticks after application. One baseline repeat uses a bomb. The action-start window must be checked, not just the future endpoint.
- A later sparse-looking screenshot makes V1 choose stay. Collisions occur 109/138 ticks after application; baseline's small right corrections avoid them. Staying is not inherently safe: the next idle interval needs its own threat forecast.
- In a human observation, one turn-guard repeat moves right 25 frames, gains shot damage, then collides 133/162 ticks after application; the baseline stays safely. A profitable final firing column must be rejected if its later stationary residence is unsafe.

These findings are diagnostic only. No case IDs, timings, coordinates, human future controls, labels or future bullet locations appear in either actor prompt. Both candidates apply general rules to screenshots and historical latency.

## Hypotheses and frozen selection

`safe_intercept_v2` preserves a compact delay-plus-flight/turn heuristic, followed by an explicit veto over action start, travel and stopped endpoint until the next slow response. It explicitly requires the stay candidate to pass the same safety check.

`safe_corridor_v2` starts with a hard safety filter at those three stages; it then chooses useful shot coverage among safe options. It forbids crossing a stream or accepting a closing idle gap merely for better alignment and allows safe partial correction. Available bombs remain proactive choices, not automatic actions.

Collection: baseline plus both candidates × 12 cases × 2 repeats = 72 subscription calls, aggressive minimal envelope, Sol/low. Private rollout scoring uses the unchanged median/P95 delays (2.69135/3.170205 seconds), 180 logical-tick horizon, warmup/steady-shot diagnostic, and original safety/resource gate. Ranking must first pass gross hits/deaths/bombs/alive-nonshooting no increase, then improve sustained shot damage/miss intervals. Never loosen the gate after seeing results. If neither passes, retain baseline and continue diagnosis; no paid promotion based only on aggregate damage. Any later promotion requires frozen whole episodes and actual uninterrupted API 1x validation.
