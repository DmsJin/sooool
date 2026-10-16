# Deliver complete model actions before response completion

Native gameplay now validates the accumulated response.output_text.delta text
and offers the complete action JSON to the existing executor as soon as it is
valid. No partial row is executed. IDs, keys, literal absolute times and expiry
values are passed through unchanged; no note detection, dedup repair or timing
correction was added. The task prompt and model/tier/output cap are unchanged.

The created/in-progress event must identify the requested model before delta
submission. An explicit wrong tier blocks submission; an omitted tier is checked
against the actual final response. Missing early identity information falls back
to submission at the completed event. Final model/tier/status checks remain.
Event formats follow the official OpenAI Responses streaming documentation:
https://developers.openai.com/api/reference/resources/responses/streaming-events

The early callback does not finish the request. The same coroutine continues
reading the stream, retains its concurrency slot and conservative budget
reservation, then durably settles reported usage. Provider.close waits for
outstanding calls. There are no detached accounting tasks or retries. Generic
APIProvider.act callers still wait unless they explicitly supply both on_action
and an action schema validator; native gameplay opts in by default.

An already-offered action cannot be retracted when later text changes, the
response becomes incomplete, or transport fails. Such failures are recorded,
including the offered literal text and callback outcome; callbacks are never
repeated. Unknown charges retain their reservations. A failed executor callback
also drains the stream and accounts usage before surfacing the failure.

Metrics have distinct meanings:

- action_ready_s: HTTP start to complete schema-valid JSON offered to the callback.
- delivery_stage: json_complete_delta or completed_event fallback.
- action_callback_s: time spent handing the exact plan to the caller.
- action_delivered: callback returned successfully (profiling uses a no-op callback,
  so this field alone does not mean keys were pressed; native receipts provide that evidence).
- latency_s: original full-stream duration, retained for historical comparisons.
- completion_event_s: time to the terminal response event.
- pre_http_s, settlement_s, total_provider_s: retain their accounting meanings.

Native request rows preserve both early delivery/receipt and final metadata.
Online gameplay RTT history uses readiness when delivered early. Serial profiling
also observes readiness with a no-op callback and still awaits each complete
request/accounting cycle before issuing the next. It never applies actions.

Joint native profiling uses action readiness for delivery, and separately
estimates full request occupancy from public receipt/provider timings. The
virtual simulator keeps the slot occupied until that correlated drain/settlement
time; it cannot invent capacity by freeing an actor at action delivery. Old
profiles retain their original behavior. A delivered action whose stream failed
without final timing metadata makes profile extraction fail explicitly; it is
not silently discarded into an optimistic completed-call distribution.

For a full-response control, pass --wait-for-completion to BOTH model_freeze
and model_native. The selected early_actions mode is frozen in the manifest.
Existing frozen sources cannot be reused after this transport change; generate
a new freeze and held-out chart. Policy output format is unchanged.

Validation:68 local no-paid-call regression tests passed, including real httpx
SSE byte fragmentation with an open gated HTTP body, early native executor
submission, late failures and cancellation, retained budget reservations,
unchanged literal times, no repeated callback, and occupied simulation slots.
No paid API call or gameplay score is claimed for this transport revision.
Actual latency savings and native gameplay accuracy have not been measured.

The research runtime under /tmp/dfjk-model-timing on Ubuntu was synchronized.
Sixty-six applicable offline tests passed there on Python3.10. Two existing
legacy deadline tests were run locally only: the initial broad remote attempt
exposed an asyncio.TimeoutError versus built-in TimeoutError expectation
difference on Python3.10, unrelated to this transport change. Missing test
support files were synchronized before the successful66-test remote run. Both
attempt logs are retained. The API stream/new cancellation tests passed on both
hosts. No remote paid call or test service was started; paid fencing remained.
