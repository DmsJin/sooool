> **Retained source-harness research record.** This report/protocol describes its original experiment stage. “Current”, “ongoing”, “selected” and acceptance statements below belong to that stage; use the [selected Touhou learning record](../../../docs/touhou-research-record.md) for the released policy, actual API wins and current launcher status. The original report follows unchanged.

Historical early-delivery calibration uses completed real API race logs, not a
fastest serial API benchmark. Reproduce the original successful episode profile:

```sh
python -m research.early_control_delays /path/to/api-real-human-adaptive-early-v1-seed1 \
  --terminal-tail-policy durable_plus_median_poll_lag \
  --output /new/path/profile-control-early.json
```

The original episode has 19 four-way cohorts (76 candidates): one one-image
cohort, one two-image cohort, and 17 three-image cohorts. Matching is strict;
there is no implicit image-count fallback. Only the timing distribution and
aggregate control-age statistics are visible to the actor, never its sampled
per-request latency, screenshots from this historical episode, or future state.

Readiness is callback-start plus measured callback duration. The callback writes
and fsyncs the complete validated action before publishing it. Callback return
therefore bounds durable publication from above; these logs did not separately
record exact fsync/publication timestamps. Browser capture time is aligned to the
Python clock using the episode median apply-clock offset, so readiness vectors
include an alignment approximation. This is explicitly different from measured
selected-action age, which directly subtracts two browser clock readings and
reproduces P50=2.69135 s and P95=3.170205 s for 18 applied actions.

Slot release uses coordinator `completed_wall_s`, retaining its polling delay
and the full terminal billing tail. The final four requests were drained after
gameplay, so their coordinator slot-release times are censored. By default this
causes an error. `exclude` removes the entire censored cohort. The explicit
`durable_plus_median_poll_lag` policy retains its measured readiness vector and
models only its terminal slots as terminal-result durable time plus the median
observed coordinator polling lag. Provenance names each modeled tail cohort,
source hashes, and the exact model; this is not a new measured terminal clock.

Set `simulation_terminal_hold: true` together with `mode: sim` and
`cohort_delay: empirical_joint` to consume the paired readiness/terminal vectors.
A candidate can apply at readiness, but occupies its virtual capacity slot until
terminal release. Whole rows are sampled together, retaining within-cohort
readiness correlation, slot skew, and terminal tails. The default remains false
and preserves the earlier scheduler behavior and prompt bytes. Ready futures
still block the subscription simulator until their actual answer is available;
subscription wall speed never leaks into the assigned virtual clock.

For a new candidate prompt, first obtain its strictly serial API marginal
profile. A minimal declared transport model would rank each historical
candidate's **API legal-action duration** within its image-count stratum, map
that rank to the new serial legal-action marginal, retain that candidate's
capture-to-network and callback-publication residuals, and retain its jointly
paired terminal-minus-ready tail. This models prompt-dependent latency; it does
not measure new concurrent API timing. One-sample strata have no measured tail,
so their constant marginal model must be explicitly disclosed. Do not silently
map terminal `total_s` as if it were early legal-action readiness. After actual
real-time evaluation, recalibrate from its new observed early/terminal clocks.

The transport model is implemented separately, without changing the historical
calibrator or existing defaults:

```sh
python -m research.early_transport_delay \
  --joint /path/profile-control-early.json \
  --serial /path/new-candidate-serial.jsonl \
  --expected-serial-count 21 \
  --source-episode /path/api-real-human-adaptive-early-v1-seed1 \
  --output /new/path/profile-control-new-candidate-modeled.json
```

`--source-episode` is optional when original recorded source paths still exist;
repeat it for multiple episode basenames when moving the logs. The CLI verifies
all original core-file and early-action hashes, reconstructs original joint
vectors, and requires exact model/tier/effort/output-cap/image-detail/schema
identity between historical and new serial calls. Every historical image-count
stratum must occur in the new serial set; no fallback or implicit replacement
exists. `--expected-serial-count` is mandatory to reject partial calibration.

The output kind and control-age kind are both
`modeled_early_prompt_transport`. `actor_context` contains honest explanatory
text for a policy prompt branch. Actor control-age statistics are minima of the
modeled readiness cohort plus application overhead, not the historical measured
selected-action ages. Source timing metadata, ranks and modeled tails remain in
the offline audit; never expose a sampled per-request delay to the game actor.
The tool makes no network requests and refuses to overwrite frozen outputs.
