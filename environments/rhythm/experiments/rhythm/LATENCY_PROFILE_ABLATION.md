# Latency profile ablation on v19

The user asked whether the latest simulation still scores well without supplied
latency profiling, and clarified that visual calibration should remain.
On this matched case, removing the prior latency numbers and live RTT history
reduced performance substantially. A generic unknown-delay reminder did not
restore the score. This does not establish necessity for other strategies.

| Actor input | PERFECT | GREAT | GOOD | MISS | Empty | Max combo | Median action lead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Prior latency numbers and live RTT | 49 | 1 | 1 | 1 | 2 | 20 | 1372ms |
| Both removed, RTT-dependent reminder also removed | 8 | 2 | 1 | 41 | 0 | 3 | 543ms |
| Both removed, generic unknown-delay reminder retained | 10 | 0 | 1 | 41 | 0 | 3 | 604ms |

All three completed the same52-note30-second chart, using identical sampled
frame ages, API delays and additional transport delays, seed79,140ms request
cadence,12 actors and the minimal subscription outer. Each issued203 requests,
dropped12 at capacity, delivered191 before episode end, had zero provider
errors and verified unchanged source. These are one episode per arm on a
previously tested chart, not new held-out/native acceptance or a statistical
equivalence study. The original chart and timing-profile hashes are preserved
in comparison.json.

Blind inputs omit the RTT field altogether. Their memories remove the explicit
1456ms total/46ms overhead figures and the reference to an1800ms cutoff. Visual
geometry/speed, literal timing arithmetic, the previously tuned150ms expiry,
dedup strategy, public clocks, pending commands and acknowledgments remain.
The first blind variant also removes the instruction referring to RTT; the
third arm restores a nonnumeric reminder: "Response delay is unknown; weigh
lead against that uncertainty." Every request prompt was audited. The model
may infer delays from remaining public observations; this is not an untrained
policy or removal of all historical tuning.

The no-profile actors chose much nearer notes: median scheduled lead543/604ms
versus1372ms in control. Final executor receipts show43 expired-before-admission
commands in each no-profile arm versus one in control. This supports a change
in model planning ahead of delayed delivery, rather than a transport failure.
The executor still forwards the model's literal times without correction.
The study removes prior profiling and online RTT together; their individual
contributions and an online-learning replacement were not tested.

No paid API calls were made, and the cumulative paid ledger bytes are unchanged.
Seven codec/causal-runner tests passed, including exact preservation of other
public fields when RTT is omitted. Initial SSH startup failures occurred before
any episode began and are preserved but excluded from the three completed runs.
Evidence: ignored durable model-timing/latency-profile-ablation-v19 contains
manifest.json, exact memories/commands, all prompts/images/decisions, immutable
run freezes/summaries, analysis.py and comparison.json. --hide-rtt is optional
and affects only the lean joint-simulation actor input; callers must separately
remove profile values from supplied memory. Existing defaults remain unchanged.
