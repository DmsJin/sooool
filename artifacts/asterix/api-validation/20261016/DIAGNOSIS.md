# Diagnosis of the interrupted API attempt

## Confirmed

The previous client's `Terminal response usage missing` error conflated distinct
conditions. Offline reproductions showed that a top-level SSE `error` event was
ignored, `response.failed` without usage lost its provider error code, a stream
without any terminal event looked like a terminal event missing usage, and HTTP
200 with a non-SSE content type also produced the same generic error. A failed
terminal with known usage settled its bill correctly but still hid the error code.
Five tests covering these distinctions failed against the old client and passed
after the fix. An additional end-to-end test verifies that Asterix retains the
shared client's safe diagnostics in `failure.json`.

The fix preserves unknown-usage blocking and all completed-usage settlement.
It records request/response IDs, terminal kind/status, media type, provider error
code, incomplete reason and event counts. It does not record provider error
messages, raw bodies, credentials or private reasoning. The existing early-action
schema, action holding and V28 gameplay prompt are unchanged.

A separate **read-only** `GET /v1/models/gpt-6.1-sol` returned HTTP 200 and that
exact model ID. See `model-access-check.json`. No generation request was made by
this lookup. It establishes current model-metadata access, not successful
Responses inference, Ultrafast access, sufficient credit or retrospective billing.

## Not recoverable from the original record

The failed request's raw stream, provider request ID and detailed provider error
were not retained by the old client. Its original upstream cause is therefore
unknown. The reproduced rate-limit/server-error cases are synthetic examples,
not evidence that either occurred in the actual request.

The original ledger remains blocked, with actual cost unknown and US$0.27747
conservatively reserved. Neither the historical attempt nor its ledger was
rewritten. No further paid Responses call was made during diagnosis. A future
inference retry requires resolving that outstanding usage first and must retain
the new diagnostics; it cannot be reported as a successful 60-second result now.

Validation before integrating current main: 73 root tests passed with 5 skipped;
149 shared research tests passed with 6 skipped. After integrating current main,
81 root tests passed with 5 skipped. These are offline tests, separately from the
model-access lookup. The original live ledger and archived ledger still have
identical SHA256 hashes; the unknown reservation has not been changed.

Protocol reference: [OpenAI Responses streaming events](https://developers.openai.com/api/reference/resources/responses/streaming-events).
