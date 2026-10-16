> **Retained source-harness research record.** This report/protocol describes its original experiment stage. “Current”, “ongoing”, “selected” and acceptance statements below belong to that stage; use the [selected Touhou learning record](../../../docs/touhou-research-record.md) for the released policy, actual API wins and current launcher status. The original report follows unchanged.

# Visual tracking and delayed-dodge development set

The objective remains defeating Kaguya at the original 1x game speed. Surviving the timer alone is a failure. All player decisions belong to GPT; the executor only applies its requested keys and durations. Physics, hitboxes, bullet timing and difficulty stay unchanged.

## Frozen comparison

Compare `grounded_macro`, `tracking_dodge_small`, and `tracking_dodge_adaptive` on identical observations and repetitions. Use the same schema, screenshot history, held keys, known applied schedule, past model estimates (if available), and measured control-age context. Set `pixel_controls=true` for all three so the static movement constants are shared. Freeze inputs, provenance and evaluation rules before collecting answers. Historical delay is provisional for the longer new prompts; promotion to a paid realtime attempt requires strictly serial API re-profiling of that exact candidate.

The small candidate prefers focused 8–24 screenshot-pixel nudges; the adaptive candidate can make longer focused corrections when a small nudge would leave shots missing. Neither forces movement while aligned, nor forbids a necessary escape. This distinction tests the user's small-step hypothesis instead of treating it as proven.

## Cases to include

1. Clear lower corridor, boss displaced left: a safe focused correction should keep firing and stop before overshooting.
2. Same situation displaced right: no habitual one-direction response.
3. Already aligned: staying and firing can be correct; unnecessary oscillation is undesirable.
4. Boss near a visible turn: do not extrapolate stale drift indefinitely.
5. Enemy bullets approaching the delayed player location: evasion has priority over tracking.
6. A bullet looks close but moves away, or a wide gap stays open: do not invent an emergency or spend a bomb without cause.
7. A clear gap now closes during the response delay: judge arrival time and the whole path.
8. No bombs, or player absent after death: do not rely on an unavailable or non-edge-triggered X.

Cases are development examples, not independent held-out evidence. Adjacent frames and clips from the same run are correlated. Keep any final evaluation episode/seed separate from development; never call an already-inspected run held out.

## Input and labels

The playing model receives only original rendered historical screenshots and allowed clock/control/delay metadata. Never include future frames, precise engine positions or velocities, seed-derived trajectories, recommended paths, outcome labels, human future inputs, or private rollout scores in its prompt. Audit files and private labels must be separate from the model's input bundle.

Keep source episode, decision/frame identifiers, chronological screenshot frames and content hashes. One observation admits several safe useful actions; do not grade by equality to a single human or scripted move. Report repeated answers to expose policy variance rather than selecting only a favorable answer.

Private counterfactual scoring, when available, must restore the original engine state by replaying the actual executed prefix, continue the known control schedule during the assumed delay, and only then apply the model's returned plan. Fix the post-action horizon and resource scoring in advance. Report hits/death, damage dealt, bomb use and displacement separately; a small move is not a win if it continually misses. Scores do not get fed back into a live episode as an automatic controller.

## Human demonstration

Record an original-speed human run in this exact environment: original game frames, key edges with actual logical/visual timestamps, per-step held controls, pauses/focus loss, seed/config, video and private final state. Replay recorded controls and verify the final deterministic state before treating the recording as a reference.

Two comparisons answer different questions:

- Whole-run comparison: human and Sol independently play the same seed from reset. It compares outcomes and behavior; after the first different action the states diverge, so later actions are not matched-state labels.
- Matched-state cases: replay a human prefix, give Sol only screenshots available at the chosen observation time, let the game advance through the measured delay, then apply Sol's decision. Future human inputs and future frames remain hidden. Compare safety and useful shooting against the human reference, allowing multiple valid actions.

A human without artificial delay sees and acts much faster than Sol. Exact human key matching is therefore not the objective. An optional separately labeled delay-matched human baseline can isolate latency from strategy, but must not be confused with ordinary human play. External TH08 videos are qualitative references only: their original bullet density and physics differ from this simplified environment.
