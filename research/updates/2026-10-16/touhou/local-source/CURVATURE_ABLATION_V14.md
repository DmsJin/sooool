# Prepared short-horizon trend ablation

Two untested candidates add the same short reasoning paragraph:

- `tracking_dodge_curvature_v14` is frozen v2 plus the paragraph.
- `tracking_dodge_speed_curvature_v14` is v13 plus the identical paragraph.

This prepares a later four-arm factorial comparison of original v2, its two-
sentence speed-preference revision, the trend paragraph, and both together.
No experiment was started, and no default candidate was changed.

The paragraph asks GPT to estimate two velocities from three chronological
images and their actual time gaps, estimate acceleration using the separation
between the interval midpoints, and compare a short-horizon second-order
projection with constant velocity. It explicitly treats acceleration as noisy
and changing, rejects unbounded extrapolation or invented history, and asks the
model to consult its own observed turns. Initial spawn position is not a motion
boundary. Existing full-path, parking-wait and Bomb priorities remain unchanged.

Motivation is the private diagnostic that near-zero local velocity can precede
a turn and increasing speed. This is a hypothesis about useful instructions,
not proof of a model's hidden reasoning or a claim that actual boss motion has
constant acceleration. There is no engine formula, private example coordinate,
future trajectory, action table or unique answer in either task prompt.

All calculations and action choices remain GPT's. The program appends text only;
it computes no velocity, acceleration, target or risk. Both candidates keep the
original grounded four-field JSON contract and source cohort wording, with no
audit forecast fields. Engine, Gym state, reward, scheduler, controls, original
v2/v13 policies and separately frozen v12 experiment sources are unchanged.

Only structural tests and mock tests ran: no model/API call, service startup,
screen or episode. A later frozen experiment must independently assess safety,
resources and ordinary shot contact before any promotion.
