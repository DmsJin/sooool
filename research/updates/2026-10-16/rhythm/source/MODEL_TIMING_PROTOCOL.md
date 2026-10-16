> **Historical research snapshot — not the active Rhythm workflow.** This is the earlier 30-second held-out protocol. The current 17-second policy receives public receptor/speed and screenshot-time calibration; its executor still preserves model-authored absolute tap times. Use the [current workflow](../../../../../docs/rhythm.md) and [selected case study](../../../../../docs/rhythm-autoresearch.md). The original report follows unchanged.

# Model-owned tap timing benchmark

GPT receives full-board screenshots, external monotonic capture brackets, the
current external clock, raw pending commands, a bounded tail of raw receipts (24 in initial research, 8 in native validation), raw
RTT samples, and a model-authored general visual calibration/strategy memory.
It receives no chart, note coordinates, audio clock, hit-line coordinate,
travel time, or program-calculated target timestamp. The memory may contain
physical estimates inferred by GPT from screenshots; the program never applies
those formulas.

The action is a finite JSON transaction containing at most 12 literal taps:
`{version,cancel_ids,taps:[{id,key,at_ms,expires_ms}],replace_pending?}`.
No loops, scripts, tracking rules, conditions, or state-triggered execution are
accepted. Every plan comes from a fresh visual model request. Generic stable
IDs, explicit cancellation/replacement, queue versions, and expiry are part of
the actuator protocol. Identical retained commands keep their original times;
executed IDs cannot replay. Newer versions do not implicitly replace a queue. Out-of-order additive plans
are accepted with first-writer IDs; stale replacements/cancellations reject.
Snapshot versions remain monotonic; per-command receipts preserve the originating
transaction version.

The executor reads only its external clock and the supplied queue. It executes
at the first timer tick at or after `at_ms`, if not later than the model's own
`expires_ms`. Late admission inside that interval executes immediately with
both original and actual time logged; later admission expires. It never
corrects timing from pixels, game state, audio, latency, or target matching.
Native timer precision is actuator assistance and must be reported separately
from model prediction accuracy and plan delivery latency.

Paid profiling is strictly serial and uses the real API. Subscription research
uses measured API delays in a causal virtual clock. Model answers cannot affect
the game before their simulated delivery event, regardless of subscription
wall time. Virtual scores are research evidence, not real-time acceptance.

Use `--joint-profile` for full transport-condition research. A trusted calendar
captures each image before its request by the sampled frame age. At request
time, the model receives that retained past image and the current public queue
snapshot. Its answer is inspected and submitted only after both the sampled
API RTT and extra transport delay. Joint tuples preserve within-request
correlation; their values and future calendar are never actor inputs. This
corrects the earlier RTT-only simulation's optimistic fresh-frame and zero
transport-overhead assumptions. Random resampling does not preserve temporal
bursts. Each profile represents its recorded source configuration; sensor, host
or load changes require fresh measurements.

Freeze the policy source and model-authored memory before drawing fresh secret
held-out chart seeds. Only the trusted renderer/evaluator receives these charts;
subscription policy workers have no tools or mounted chart files. Native API
validation runs the ordinary game and music clock at 1x, without simulator
injection. Report complete 30-second outcomes, MISS, score, empty presses,
request latency, and actual versus requested execution time. The current target
is a native full combo: zero MISS and max_combo equal to all 52 notes, with a
complete original-speed episode and valid clock diagnostics. Zero MISS alone
is insufficient because empty presses can reset the combo. All-PERFECT is optional.

All paid requests share the pre-existing cumulative ledger, explicitly increased by the user to USD49.886709. Unknown-cost
requests keep conservative reservations. Never create a fresh experiment ledger
to recover spending room.
