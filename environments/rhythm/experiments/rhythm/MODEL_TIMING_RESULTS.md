# Literal model timing: research log

Status: native solve remains unverified. Do not use the previous assisted 100%
results as evidence for this benchmark. The current native target is a complete
30-second, 1x, freshly generated held-out chart with at most two MISS.

| Variant | Mode | PERFECT / GREAT / GOOD / MISS | Empty presses |
| --- | --- | --- | --- |
| v4 | Subscription, sampled API delays | 41 / 1 / 0 / 10 | 1 |
| v5 | Subscription, sampled API delays | 52 / 0 / 0 / 0 | 1 |
| v5 | Native API, fresh held-out chart | 18 / 10 / 4 / 20 | 4 |
| v6 | Subscription, sampled API delays | 51 / 0 / 0 / 1 | 0 |
| v6, changed external clock origin | Subscription, sampled API delays | 50 / 0 / 0 / 2 | 1 |
| v6 | Native API, fresh held-out chart | 33 / 5 / 1 / 13 | 0 |
| v11, minimal outer | Subscription, 149 empirical API delays | 52 / 0 / 0 / 0 | 0 |
| v11, minimal outer, 240ms cadence | Subscription, same empirical delay distribution, seed 49 | 52 / 0 / 0 / 0 | 0 |
| v11, minimal outer, 420ms cadence | Subscription, v6 empirical delays, seed 49 | 45 / 0 / 0 / 7 | 0 |
| v12, minimal outer, 420ms cadence | Subscription, fresh chart, v6 empirical delays, seed 49 | 51 / 1 / 0 / 0 | 0 |
| v12, minimal outer, 420ms cadence | Subscription, same chart, all 431 v11 native delays, seed 61 | 44 / 2 / 0 / 6 | 0 |
| v12, minimal outer, 300ms cadence | Subscription, same chart, all 431 v11 native delays, seed 61 | 48 / 1 / 1 / 2 | 0 |
| v11 | Native API, fresh held-out chart | 37 / 5 / 4 / 6 | 0 |
| v11, receipt deltas | Native API, another fresh held-out chart | 35 / 6 / 2 / 9 | 4 |
| v12, 300ms cadence, certified reservations | Native API, another fresh held-out chart | 8 / 2 / 2 / 40 | 3 |
| v12, 300ms cadence, full joint delays | Subscription, replay of failed native chart, seed 61 | 15 / 4 / 4 / 29 | 0 |
| v12, 120ms cadence, full joint delays | Subscription, same replay chart/profile/seed, 16 actors | 26 / 4 / 11 / 11 | 0 |
| v12, 60ms cadence, full joint delays | Subscription, newly generated chart, 28 actors, seed 61 | 37 / 10 / 2 / 3 | 2 |

The initial queue rejected out-of-order additive plans when a newer empty plan
arrived first. Generic first-writer ID semantics now accept these additions;
stale replacement/cancellation still rejects. No tap times change.

Initial screenshot capture brackets had median 167.8ms in the first native run.
A generic CDP compositor sensor now provides full-board PNGs with browser frame
swap timestamps. Subtracting public performance.timeOrigin places observation
timestamps in the actuator clock domain; action timestamps remain literal.
In isolated remote tests the frame age was 23-28ms and capture calls took 6-8ms.
The v6 native run had median frame age 28.6ms, API median 1.259s, P95 1.725s,
and a 5.011s maximum response. Its cost was USD3.331977. All 39 executed taps
hit notes, while 13 IDs first arrived beyond their model-chosen expiry.

GPT-authored strategy revisions address repeated pending plans, prioritization
of newly visible notes, finite close-pair chunks, and explicit expiry. A lean
wire codec reduces input/output tokens without computing any action time.
Subscription outcomes remain simulations; only native API runs can establish
real-time acceptance. Failed runs and frozen source snapshots are retained.

Durable evidence is under ../rhythm-autoresearch-evidence/model-timing (outside
this worktree). Paid requests use the original cumulative USD30 ledger,
including conservative reservations for unresolved earlier requests.

A shared long task-policy prefix was also tested in eight serial API requests.
All eight reported zero cached input tokens despite the common prefix; median
latency was 1.681s and costs rose. This attempt was not adopted. A separate
subscription-only randomized paired test now evaluates the user's minimal
Codex outer prompt while preserving the full gameplay task, pixels and action
format. It does not spend the paid API budget.

The user selected the minimal subscription outer after the paired pilot. The
new full subscription episode achieved 52 PERFECT, full combo and zero empty
presses in 213.8s wall time, with unchanged policy source. Native validation
still failed; no solve is claimed. Receipt cursors now avoid retransmitting
the full acknowledgment history. Clock-health drift is measured while audio
is still playing, because sampling an already ended clip overcounts time
after its clock clamps to the clip duration. This changes diagnostics only.

Reducing subscription observation cadence to 240ms retained 52 PERFECT and
zero empty presses with 126 requests, versus 251 in the previous 120ms run.
The full episode took 211.2s subscription wall time, had no provider errors,
and verified unchanged policy sources. This is still a virtual-delay result.
Two overlapping 360ms experiments failed during SSH worker initialization,
before entering the game; they are infrastructure failures, not scored runs.
Subsequent experiments run with fewer workers to leave SSH channels available.

The native audit found accurate visual time estimates but many redundant
one-tap answers, late returns and expiry failures. In the transport run, three
missed targets had a response within the game's 180ms judgement window but
beyond the model's own 120ms expiry. Strategy revisions may choose different
literal expiries; the executor continues to preserve every model timestamp.
The remaining conservative paid allowance is USD1.818060. Previous uncertain
charges remain reserved; no reservation is released from inference alone.

GPT authored v12 in exactly one minimal subscription revision call. Its raw
815-character response is preserved without edits alongside the full prompt,
worker configuration, source hashes and usage. It chooses up to two future
taps and a literal expiry 180ms after its predicted tap time. The executor is
unchanged. A new secret chart was generated after freezing this memory and
runtime; actors received screenshots only. At 420ms cadence this chart first
passed with 51 PERFECT / 1 GREAT, but failed with six misses under the newer
431-sample native delay distribution, including its 6.067s maximum. Moving to
300ms cadence reached the two-miss simulation threshold with 101 calls in
168.0s wall time. All three v12 runs had zero provider errors, zero empty
presses and unchanged policy sources. These are development simulations, not
native API acceptance; another fresh chart is required for that acceptance.

Official documentation confirms a Responses input-token counting endpoint:
https://developers.openai.com/api/docs/guides/token-counting . It has not been
adopted: the reviewed page does not establish counting-request billing, and
the vision sizing table does not explicitly cover gpt-6.1-sol. Existing
conservative financial bounds and old uncertain reservations remain intact.
No paid API calls were made during those subscription cadence and strategy experiments.

The counting endpoint was subsequently tested once with the exact model,
image dimensions, detail and message framing. It returned 428 input tokens
for one 390x844 high-detail PNG and empty user text. Its original USD0.184320
reservation remains uncertain: this experiment does not assume the counting
endpoint is free. For matching single PNG inputs only, new inference requests
reserve that framed image count plus the complete UTF-8 prompt byte length
and 128 tokens of margin, charged at the existing pessimistic input rate and
full output cap. Unsupported framing/geometry retains the original large
bound. All old uncertain charges remain reserved. Four financial-bound tests
pass, including malformed PNG/certificate and unknown-geometry fallback.

Code, memory and the financial certificate were frozen before generating
another secret chart (SHA256 8220395776cef3669328531ccf708f7ab89420604003e88ee707285be2528064).
Native v12 ran the entire 30.000998s clip at 1x and failed with 40 misses.
All 93 completed inference responses confirmed gpt-6.1-sol / ultrafast / low;
their cost was USD1.492644. Three additional attempts were refused by the
financial gate. Clock drift during playback was 16.6ms; the source freeze
verified. The final conservative committed amount is USD29.858904, leaving
USD0.141096. No solve is claimed.

The trusted post-run audit explains why the earlier free success did not
transfer. All 52 notes had an emitted attempt, but native API RTT median was
1535ms, frame age at observation was 149ms and snapshot-to-apply overhead
beyond the measured API RTT was another 180ms. The successful simulation had
fresh frames, no such extra delivery overhead and sampled RTT median 1319ms.
Of 123 literal tap predictions, 107 arrived past their model-authored expiry;
37 notes had every corresponding prediction expire. Predicted target times
were also consistently late (median +57ms under the trusted clock mapping).
These aggregate diagnoses never enter an acting model as hidden chart values.

The sensor copied the cached image before awaiting a public-clock RPC, so it
discarded fresher compositor events received during that round trip. It now
selects the latest raw frame after the await without changing its timestamp.
A regression test covers this asynchronous update. In a separate native
browser stress test with a synthetic 120ms clock-RPC delay, 30 paired samples
reduced median frame age from 293.9ms to 95.2ms. This test made no model/API
calls and is not gameplay acceptance. The sensor fix has not had a complete
native API score validation. Future simulations must include measured image
age and extra delivery overhead, not just sampled inference RTT.

The complete native source freeze, PNGs, requests, results, certificate and
budget/API records are preserved in model-timing/native-v12-archive. Trusted
aggregate diagnoses are in native-v12-certified-audit.json; sensor measurements
are in sensor-rpc-delay-comparison.json. These artifacts live in the durable
evidence directory outside the worktree.

The new joint-condition simulator extracts all 93 completed native v12 timing
tuples: raw frame age at observation, API RTT and snapshot-to-apply overhead
beyond that RTT. Three refused requests have no completed metadata and are
explicitly recorded as excluded. The extractor reads no chart, note position
or model tap time. Joint tuples are sampled together, preserving within-row
correlation; temporal correlation and native visual timing bias are not yet
reproduced. The pre-fix frame-age samples may overstate the corrected sensor's
delay. Neither this limitation nor the native failure is hidden from results.

A trusted event calendar captures each image at request time minus its sampled
age, retains that image, and supplies it alongside the current public queue
at request time. It reads each model answer only at API RTT plus transport
overhead and sends the literal parsed plan unchanged. Three causal tests
verify stale pixels/current snapshots, delayed answer admission, capacity
drops, private-field exclusion and intact joint sampling. Together with the
existing causal runner test, four tests pass; fixture scores are not game
performance evidence.

Replaying the already tested native chart (not a new held-out test), unchanged
v12 policy at 300ms cadence now misses 29 notes in the full-condition simulation.
At 120ms cadence and 16 actors it misses 11, with 240 issued requests and 11
capacity drops. Wall times are 181.3s and 268.1s. Both episodes have no provider
errors, no empty presses and unchanged sources. These individual trials show
the importance of the missing delays; they do not establish reliable native
transfer or isolate cadence from model/sampling variability.

Current settled API charges total USD20.460654. Uncertain reservations total
USD9.398250, leaving USD0.141096 under the USD30 ceiling. Two read-only attempts
to query organization costs returned HTTP403 with the existing project key;
no model inference was requested. Nothing was released from the ledger. The
user has been asked whether to reconcile actual billing, change the budget,
or restrict further work to free research. No budget change is assumed while
that choice is pending. Billing access evidence is billing-access-check.json.

One further free trial froze v12 and the 60ms/28-actor runtime before generating
another chart (SHA256 c9af4798ba1931d6e4adc96732d415536aa016bfd28498307f5b510d7b89e180).
Under the same measured joint-condition distribution it completed with three
misses and two empty presses: still a failure, not a relaxed acceptance.
It issued 444 requests, dropped 57 at the actor-capacity limit, had zero
provider errors and verified unchanged sources. Subscription wall time was
434.4s. This is a single virtual trial on a different chart, not proof that
native latency remains unchanged at 28 concurrent requests.

Exactly one additional free minimal subscription call re-examined native
obs0004/0005/0006 and their raw public frame clocks. No chart values or trusted
target-time error was supplied. Its unedited 2240-character v13 memory is
preserved with complete input/configuration/response provenance in
revision-v13-nativevisual; it independently estimates provisional speed .327
pixels/ms from three frames. It is not adopted or claimed better: this longer
prompt has no new serial API latency calibration or gameplay validation.

A copy-only ledger benchmark identified avoidable event-loop I/O. On the
292842-byte ledger, snapshot/reserve/settle initially had medians of
21.99/21.43/21.14ms. Snapshot now retains its lock/validation without rewriting
the JSON; the second benchmark measured 2.79/20.49/20.88ms. Both benchmarks
verified the authoritative ledger bytes were unchanged and made no model
calls. These are independent microbenchmarks, not an end-to-end latency claim.
API financial operations now run via asyncio.to_thread; durable reservation
still precedes HTTP transmission and durable settlement precedes returning
the model answer. Payloads and tap timestamps remain unchanged. Paid entry
points also refuse a fresh run directory without the existing cumulative
budget.json. Twenty-three financial/guard/scheduler tests pass, including
concurrent reservation limits and durable-order checks. These I/O changes
have not had a complete native API gameplay validation.

The user subsequently raised the cumulative authorized paid ceiling to USD40
and requested a true native full combo. The existing ledger was migrated from
USD30 with every prior request unchanged; no uncertain charge was released.
The ledger default remains USD30 for compatibility; paid entry points explicitly
open the persisted limit, bounded by the newly authorized USD40 maximum.
The native CLI now defaults to zero misses and verifies the frozen acceptance.
A full-combo claim additionally requires max_combo to equal all 52 notes.

Local native v14 at 120ms/16 actors failed: 52 MISS, zero hits, with 0.860s
audio/external-clock drift, so it also failed clock validity. Its 105 attempted
requests included one ReadError; the reservation remains uncertain. A full
ledger-copy concurrency diagnostic measured median snapshot/reserve/settle
times 0.220/0.179/0.259s and total non-sleep 0.676s. An earlier empty-ledger
diagnostic was not representative and is separately preserved.

Compact single-write JSON serialization and removal of the unnecessary final
phase snapshot reduced the full-copy benchmark non-sleep median to 0.072s;
the benchmark still included the snapshot for comparability. This preserves
locks, fsync, cumulative entries, pre-request reservation and pre-answer
settlement. API metadata now separately records pre-HTTP and settlement time.
Twenty-eight financial/ownership/scheduler/sensor/private-chart tests passed.

A second fresh-chart local native v14 trial after that change still failed:
2 PERFECT, 2 GREAT, 1 GOOD, 47 MISS, one empty press, 174 completed requests,
zero provider errors and 0.504s clock drift. It supplies no valid solve evidence.
The two local trials used different held-out charts and are not a controlled
causal accuracy comparison.

Free subscription revisions and their exact inputs/outputs are preserved in
revision-v14-nativevisual, revision-v15-nativevisual and revision-v17-nativevisual.
The v16 preparation failed before any call because a selected frame had no
issued request metadata; it was not retried in place. V17 used three actual
frames obs0020/0023/0024 with public capture clocks, prior model memory and
public outcome/receipt diagnostics, never trusted chart targets or timing errors.
Its unedited memory is 862 characters and estimates speed .332 pixels/ms.

A free Ubuntu pipeline check used fixed empty plans and a synthetic 1.5s wait,
with zero model or paid calls. Over 30s it measured 0.105s clock drift, 7.6ms
median extra delivery and 25.3ms maximum extra delivery. This is infrastructure
evidence, not gameplay success. Budget authority then moved to the guarded
remote verifier, preserving every prior remote record in the latest local
checkpoint. Remote serial v17 profiling completed eight valid responses,
median 1.666s, min 1.134s, max 2.991s, with actual sol/ultrafast/low confirmed.
A fresh-chart native v17 test at 140ms/12 actors follows this calibration.

Native v17 on the fresh Ubuntu chart completed at 1x with valid 0.0696s clock
drift and an unchanged freeze: 43 PERFECT, 2 GREAT, 3 GOOD, 4 MISS. However,
86 empty presses reset combo repeatedly; max_combo was only two. This is a
failure under both the old two-miss target and the requested full-combo target.
It attempted 206 requests: 179 completed API responses and 27 BudgetExceeded
rejections, no other provider failures. Budget rejection began at external
clock 26438.3ms (game start clock1991.1ms), censoring decisions near the end.
It cannot establish unconstrained full-episode policy performance.

Actual native v17 medians: API1.403s, pre-HTTP0.017s, settlement0.017s and
snapshot-to-apply overhead beyond API0.046s. Source/result/public-timing and
strict full-combo audits are preserved in the native-v17 archive and adjacent
audit JSONs. Budget authority returned locally after verifying all2114 base
entries unchanged; remote paid calls remain fenced. The cumulative ledger
commits USD39.896709: USD30.420774 settled plus USD9.475935 retained unknown
reservations, leaving USD0.103291. No unknown reservation was released.
The user has been asked for actual billing/usage evidence to reconcile them.

Free v18/v19 revisions use only earlier raw images/public capture clocks,
prior model memory, actual native public timing summaries and public model
outputs/receipts. Hidden targets and trusted timing errors are excluded.
V18 introduced stable IDs but a fixed1800ms lead cutoff; on another fresh chart
the full-condition free trial issued203 requests, dropped12 at capacity and
finished with52MISS and zero presses in188.7s. V19 removes that overly strict
cutoff using current native timing evidence; it is evaluated separately.
The new179-sample joint profile explicitly excludes the27 budget rejections.
It resamples completed requests only and cannot model unobserved requests or
temporal bursts; free scores still cannot establish native API acceptance.

Free v19 on its newly generated chart completed with50 PERFECT/1 GREAT/1MISS,
two empty presses and max_combo18 in239.9s. It issued203 requests, dropped12
at capacity, had zero provider errors and verified unchanged sources. Its
original passed flag refers to the legacy <=2-MISS criterion; an adjacent
strict-full-combo-audit.json records failure and preserves the original summary.
Future virtual runners now require zero MISS and max_combo52 for passed,
retaining the former criterion only as legacy_two_miss_passed. Native strict
acceptance additionally checks full completion, original rate and clock drift;
a regression test rejects zero-MISS runs whose empty presses broke the combo.
These two distinct-chart virtual trials are not a controlled accuracy comparison
and provide no new native acceptance. Full combo remains unachieved.

A matched three-arm subscription study on the v19 chart retained visual calibration
but removed prior latency figures and online RTT. Control scored49P/1GREAT/1GOOD/1MISS;
no-profile scored8P/2GREAT/1GOOD/41MISS; no-profile plus a generic unknown-delay
reminder scored10P/0GREAT/1GOOD/41MISS. All used identical imposed delay calendars,
203 requests,12 capacity drops and zero provider errors. This is one episode per
arm, not native acceptance. See LATENCY_PROFILE_ABLATION.md for input audits,
planning-lead/expiry evidence and limitations. Paid ledger bytes are unchanged.

The user requested a conditional20-second native test after a brief serial API
latency recheck, if costs stay below USD10 and latency resembles training.
Historical179 completed responses averaged USD0.01714431; at140ms cadence,
143 scheduled decisions plus six profiling calls estimate USD2.5545, with a
practical USD2–4 estimate. This is an estimate, not a new measured charge.
The existing ledger still commits USD39.896709 under its USD40 ceiling.
Automatic approval review rejected increasing that ceiling to USD49.886709
without explicit approval for the cumulative amount. The user has been asked
for that approval; the proposed increment is at most USD9.99, old unknown
reservations retained. No new paid request has been made.

Free20-second preparation now preserves the original chart generator's exact
seeded prefix, without retiming notes or changing lanes. Native validation
checks the chosen chart's actual note count rather than assuming52, freezes
the requested duration, and verifies chart bytes unchanged. Six acceptance
and private-chart tests passed. The first20 seconds of the preview were cut
without speed changes; ffprobe reports exactly20.000000 seconds.
A serial six-sample probe is prepared but has not run; no current-latency
claim or native completion is made while budget approval remains pending.

The user explicitly approved the cumulative USD49.886709 limit and USD9.99
additional cap. The ledger preserved all prior entries and unknown reservations.
Ten serial current API probes (six initial plus four distinct follow-ups, all
included) measured median1.893s, mean1.997s, population SD.620s and max3.334s,
versus training median1.403s/mean1.484s/SD.307s/max2.849s. All were actual
sol/ultrafast/low and schema-valid. Median was34.9percent slower, failing the
predeclared25percent provisional similarity gate. The conditional20-second
native game was therefore not started. All ten calls settled for USD0.173532;
no uncertain charge was released. Budget ownership returned locally with
2301 old entries unchanged and USD9.816468 remaining. See NATIVE20_RECHECK.md
for scope, the initial post-request reference-file error and evidence paths.
