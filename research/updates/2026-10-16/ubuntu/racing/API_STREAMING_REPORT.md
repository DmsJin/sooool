Current status: the final hierarchical controller has now won Level1 at1x using actual API decisions; see RESULTS.md and COMPLETION_AUDIT.json. The sections below preserve the historical streaming-development checkpoints.

# Streaming action publication

Previously the client streamed bytes but waited for SSE EOF before parsing actions.
The new live path validates each accumulated output-text delta. Once the complete
JSON action array passes shape, count and numeric bounds checks, and the returned
model/tier are verified, a separate future publishes it to the executor. The
request worker continues draining the stream and settles usage normally. Every
worker is audited before a heat transition and before the match is accepted.
Trailing output changes, stream failures or identity mismatches invalidate the
trial. Incomplete JSON and out-of-range actions never publish. Serial profiling
remains serial and waits for accounting completion before issuing the next call.

Implementation follows the [Responses streaming event contract](https://developers.openai.com/api/reference/resources/responses/streaming-events).
The actual backend returned model/tier early enough to publish before the terminal
event in all eight measured requests. Backends that omit early identity fall back
to verified completion.

## Same-request real API measurement

Eight strictly sequential requests used frozen winning-policy game prompts and
pixels, the selected minimal system, gpt-6.1-sol / low / ultrafast. Background
subscription jobs remained active. No duplicate-request A/B or cherry-picked
fastest request was used.

| Metric | Seconds |
|---|---:|
| JSON-ready median | 1.352201 |
| Stream-end median (old availability) | 1.443043 |
| Paired median saving | 0.090838 |
| Paired mean saving | 0.084925 |

All eight outputs were legal and published before response.completed. This small
sample demonstrates tens of milliseconds of transport/terminal-event savings;
it does not establish a policy success-rate improvement or eliminate the model's
inference time. Raw measurements: evidence/results/profile-stream-v1/measurements.jsonl.
Ten contract tests pass, including early-publication-before-usage and later-error
invalidation. A full optimized wall-clock match is being checked separately.

## Existing full real API baseline

Level1, slowdown5, seed101: WON, valid_trial=true, deterministic=true, no artificial
model delays. 333 actual API requests; 294/294 issued commands took effect; zero
invalid outputs. Physics ran 43.49 game seconds in217.456 wall seconds; lag P99
4.931ms. Full verification took226.050 wall seconds. This is a real HTTP/service
and API result; it is not a 1x win or an isolated Harbor submission.

Paid upper-bound ledger after baseline and eight-request stream measurement:
$8.257440 of the authorized $30 ceiling, no outstanding reservations at that point.
Global reservations continue to enforce the ceiling during subsequent validation.

## Continued research

An unseen seed4 full real API trial uses immutable racing_validator_v10 and the
early-publication path. Frozen subscription holdouts1/2/3 are independent of this
change. The bounded waypoint1x baseline completed three replay-valid losses.
Round9 tests a2 m/s^2 planned-curvature speed cap, with finite GPT-chosen waypoints,
history2, at1x on development seeds101/111/121. The executor still has no images,
map lookup or true pose. Those trials are research in progress, not solved claims.


## Completed optimized full trial

Unseen seed4, Level1/5x: WON; valid_trial=true; deterministic=true;
352 calls,351 eligible for early publication (the pre-start request deliberately
waits for full completion). All351 published before response.completed. Paired
median stream-end saving92.957ms. Zero invalid outputs; 320/321 commands took
effect (one submitted command crossed a heat/end boundary). Physics46.54 game
seconds /232.708 wall seconds, lagP99 5.284ms/max8.883ms. Total245.049 wall seconds.
All352 result artifacts verify exact model and ultrafast tier. No artificial delays.
This validates the optimization operationally; two different-seed full games are
not a causal A/B of match performance. Independent frozen subscription holdout
seeds1/2/3 all won with matching replays. Raw1x remains unsolved.

Final ledger at this checkpoint: $15.828825 upper bound, $30 limit, zero pending
reservations. No paid requests remain running. Original research continues through
three subscription-only raw1x curvature-cap episodes and the seed121 recovery.
