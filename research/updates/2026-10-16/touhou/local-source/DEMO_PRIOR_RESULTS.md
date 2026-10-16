# Sol studies a completed human demonstration

Six real, serial ChatGPT subscription turns used `gpt-6.1-sol/low` and the aggressive native wrapper. No paid API calls, full episodes or policy-file edits were made. The input was 16 unchanged original PNGs, approximately every two game seconds from2..32s, each selected at or before its target and outside spell-intro freezes. They were split3/3/3/3/2/2 into chronological batches.

Each batch included only demonstration controls already completed by that batch's last screenshot, the requested human summary (99.3%focus,22.7%moving,median5-frame moving segments,33.9s zero-hit/zero-bomb win), and Sol's own prior visual estimates/notes. No engine/source, exact entity state, future trajectory formula or current evaluation future labels were supplied. The source human run was bounded-float replay verified. Actual saved RPC prompt/schema and image hashes matched all six calls; model/effort/aggressive metadata were verified.

The final Sol response synthesized three provisional principles:

1. Preserve focused shooting with small alignment corrections rather than chasing the exact boss position.
2. Predict drift conservatively and avoid strong leading near uncertain turns.
3. Evaluate enemy bullets across the entire delayed transit and subsequent hold, not just the destination.

Sol recommended testing short focused move/hold chunks, while explicitly warning that the human's immediate-feedback5-frame corrections do not establish safe chunk lengths under a2.7s delay. It did not output a boss formula, seed schedule or timestamped action recipe. Sparse screenshots do not determine exact bullet trajectories or collision margins.

This is actual model-based demonstration study, not a claim of acquired reliable skill. The source is the same human run used for some development cases, so those images/runs are correlated training data. The next assessment must use different images or a new episode, with independent safety/damage/full-game checks. Nothing was injected into the already-frozen live API attempt.

## Candidate and audit artifacts

- `/tmp/touhou-demo-prior-learning-v1/candidate_prior.txt`: short general candidate prior suitable for a **new** development condition.
- `/tmp/touhou-demo-prior-learning-v1/provenance_audit.json`: six-turn model/input boundary checks.
- `/tmp/touhou-demo-prior-learning-v1/results/learned_prior.json`: full model synthesis and its self-estimated frame/coordinate audit.
- `/tmp/touhou-demo-prior-training-v1/bundle.json`: immutable training frame/control provenance; original PNGs remain under`images/`.

Use only the general candidate text as the proposed prior. Do **not** feed the full audit JSON, source-run frame/coordinate table or historical source controls to the realtime player; that would turn training provenance into an episode-specific lookup.

Source tooling commit`63ecba0` includes two passing tests for immutable original PNGs, six bounded batches, past-only controls and exclusion of hidden-state fields. The tiny additional exact-count estimate validation in that commit does not change the already-frozen prompts; the executed runtime source SHA is recorded separately in the audit.
