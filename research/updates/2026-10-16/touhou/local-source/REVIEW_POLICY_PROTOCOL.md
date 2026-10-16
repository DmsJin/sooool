# Reviewed visual policy iteration

This study keeps the game reward, engine, executor and one-action/48-frame
contract unchanged. GPT chooses every move, focus, shot, bomb and duration from
screenshots. Private replay scores do not choose, repair or synthesize live
commands. The default controller candidate remains tracking_dodge_safe_intercept_v2
until a new candidate passes development gates and further live validation.

Human E01–E10 notes remain intact. Assistant D01–D08 annotations are separately
marked in the review UI. No case title, rubric, original answer, annotation,
future human input, exact engine state, seed, motion formula or realized request
delay is transmitted to the actor.

Inputs freeze 18 reviewed observations with historical selected-action latency
P50=2.2042/P95=2.57086, plus eight explicitly hypothetical immediate-action
fixtures. Every candidate receives the same PNG bytes and public metadata.
The instantaneous diagnostic is not an API latency measurement or a closed-loop
zero-delay episode. Its chosen action is evaluated without future model commands.

Each round uses fresh aggressive native subscription turns, gpt-6.1-sol/low,
randomly interleaved two-repeat comparisons with 12 workers. Full game task,
observations and strict structured output remain present. Subscription wall time
is reported separately from API latency; cache differences prohibit interpreting
it as a clean prompt-only causal speed estimate.

Private evaluator first verifies complete original human/API source replays.
For each observation it replays the actual prefix, suppresses future recorded
human/API commands, and advances the frozen latency condition while retaining
only already known controls. From that private application state, the original
engine evaluates the model action for 180 logical ticks, or until game end.
Cinematic freezes are respected before application; the post-action scoring
horizon is explicitly logical time. Four sampled cloned rollouts per round are
checked against the unchanged browser research interface.

Report pre-action hits separately: a collision that occurs before any new
command could arrive is not attributed to the current command. For feasible
application states report post-action hits, gross Bomb use, ordinary shot damage,
longest firing miss, actual window length and early terminal status. Bomb damage
is separate from ordinary shot contact. Early boss kills truncate trajectories;
raw damage totals alone are not accuracy, DPS or full-window survival measures.
E and D groups must also be reported separately so one cannot hide a regression
in the other. Replaying P50/P95 from the same answer creates correlated rollouts,
not independent model samples.

Promotion gate is frozen before the refined round's answers: delayed feasible
post-action hits and gross Bomb counts cannot increase, ordinary shot contact
cannot decrease, and instantaneous hits cannot increase against the fresh paired
baseline. Passing is eligibility for further closed-loop checks, not deployment,
statistical significance, held-out generalization or a realtime win. Report
per-case regressions and repeat variance regardless of the aggregate gate.

The first 48 instantaneous outputs were superseded because their prompt wording
incorrectly described zero delay as historical API timing. Only the replacement
outputs with explicit hypothetical wording are scored. The old outputs and
hashes remain archived. Historical baseline prompt bytes are otherwise frozen;
v4/v5 retain its older single-request wording, though the runner can race a
cohort. Their historical control-age distribution and expiry semantics remain
explicit. This wording limitation is recorded rather than changed mid-batch.
