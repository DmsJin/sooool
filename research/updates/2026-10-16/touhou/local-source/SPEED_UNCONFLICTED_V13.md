# Prepared speed-preference ablation (not tested)

`tracking_dodge_safe_intercept_v2` inherits the entire adaptive tracking strategy,
including “a clearly large error in an open corridor may need a longer focused
correction” and “Reserve normal speed for a clearly necessary, visibly safe escape
rather than routine tracking.” Later forecast output instructions invite a safe
larger/normal-speed correction; mechanics v10 also says a clear route can justify
enough duration or normal speed. That leaves conflicting tracking preferences in
some inherited prompts. It is a source-level hypothesis, not evidence about the
model's hidden reasoning or the cause of any particular choice.

The prepared candidate `tracking_dodge_speed_unconflicted_v13` copies the full v2
strategy and replaces exactly two sentences:

1. Small errors get a short focused nudge; a clearly large error in a safe open
   corridor may justify normal speed.
2. Normal speed may also serve tracking when the full delayed path and stopped
   wait remain safe.

It retains every other v2 sentence, especially the Bomb rules, delayed-path and
parking safety veto, grounded four-field output, controls and cohort protocol.
It adds no forecast fields, case identities, private positions, hidden dynamics,
reference actions, new reward or code policy. Original v2 remains unchanged.

Motivation only: in the existing v11 developer screen, one mechanics/low E02
answer used a normal-speed left move and produced 180 ordinary damage with zero
hits at both fixed delays over180 logical ticks; its focused repeat produced
zero damage. These are two different outputs on tuned development data, not a
randomized test of the two sentence changes. Normal movement is not always safer
or preferable; collision safety must still cover both travel and the stopped wait.

Only preparation and tests ran. No screen, episode, model or paid API call was
started. Existing frozen v12 experiment sources were not touched. A later paired
experiment must assess safety, resource use and ordinary contact under the same
conditions before considering any promotion.
