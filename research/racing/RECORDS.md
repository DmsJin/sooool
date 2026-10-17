# Track an evaluation, not just a winning clip

Create a new output directory for every attempt. Never edit a failed attempt into a success or overwrite a prior run. Record the hypothesis before execution; the selected launcher stores it in `manifest.json`. Keep the full cohort denominator, including failures, aborts and unverified trials. An incomplete run is neither a win nor a clean loss.

## Before the run

Freeze the recipe and exact task/system prompts, observation projection, image transport, coded executor and delay profile. Record SHA256 for every selected file and the external environment source. State the changed variable, baseline, seed cohort, split, horizon/level, slowdown, cadence, pending capacity and actual worker count. Use the same conditions for a comparison; label proxy profiles and diagnostic slowdowns. Never send seeds, privileged evaluator truth, future latency draws or unknown pending answers to the gameplay actor.

Use a new copy/branch for a candidate and write a short hypothesis, for example: “Keep the stripe-relative offset while passing; compare warning counts and complete-match wins on the development seeds.” Development code and prompts may change; evaluator rules stay fixed. Record human interventions and selection decisions instead of describing them as model-discovered changes.

## During the run

Retain actual prompts and images, image hashes, returned output, requested/returned model identity and tier, observation time, proposal sequence, scheduled delivery, actual installation/effect time, rejection/stale-drop decisions, full controls and the canonical episode log. Separate valid-JSON publication, response completion and stream drain. Subscription wall time and sampled virtual delay are different measurements. Parallel episodes and parallel requests inside an episode are different concurrency conditions.

Paid profiling is serial, including drain and usage settlement. Real API evaluation runs at original wall-clock speed without imposed delays. Budget admission includes outstanding reservations; retain uncertain costs and never reset the cumulative ledger. Redact credentials and account events; do not copy authentication homes or hidden reasoning.

## After the run

Require completed execution, valid canonical trial where available, independently matching replay, unchanged scoring, actual model calls and verified inputs before accepting a result. Keep complete losses. Archive infrastructure failures separately with their cause and `won: null`; report them in the attempted cohort. A zero-model preflight is always `preflight`, never API acceptance.

`scripts/racing.py` writes `evaluation_record.json` with mode, hypothesis, recipe/profile hashes, integrity, result and source summary. `record --output <run> --record-mode <mode>` rebuilds this index from existing outputs; it neither reruns nor certifies missing evidence. The run manifest contains the resolved recipe and environment/source hashes. Keep historical outputs immutable; extend a campaign index with a new record instead of replacing old measurements.

## Decide whether to promote

1. Complete the predefined development cohort; explain whether the hypothesis survived and retain failures.
2. Freeze before fresh confirmation seeds. Reused seeds and video retakes remain reused seeds.
3. Calibrate the exact workload, including output format and concurrent occupancy, before treating simulated timing as a prediction of API behavior.
4. Run real-time API verification with the frozen candidate and bounded budget. Check model/tier, inputs, finish/checkpoint evidence, physics wall time and replay independently.
5. Publish the observed model and no-model outcomes together with their conditions. The retained selected-policy comparison is 7/7 GPT-guided wins versus 3/7 fixed grid-aware wins over the same seeds; report its mixed execution modes and timing/load differences. Separate coded tracking from GPT decisions. Use matched conditions to estimate a causal effect size; an observed performance difference may be reported with its limitations. See [the recorded comparison](EVALUATION.md#recorded-gpt-and-no-gpt-comparison).

Video is supporting evidence. State whether it is live capture or verified replay, which waits were omitted, whether speed changed, and whether heat order was edited. Evaluation tables always use original records and original chronology.
