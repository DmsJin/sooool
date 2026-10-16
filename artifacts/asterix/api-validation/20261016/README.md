# Asterix 60-wall-second API attempt

Requested condition: seed 5, V28, one in-flight request, unchanged direct actions,
gpt-6.1-sol / low / ultrafast, 12 raw FPS, 60 actual seconds (12 game seconds),
US$10 cumulative cap. This attempt did **not** complete that horizon.

- `console-import-failure/`: console entrypoint could not import the environment
  namespace before credential entry or any API request. The import path was fixed.
- `api-usage-missing/`: one request was admitted, then the response stream lacked
  terminal usage. No model action was applied. The game stopped at 25 frames,
  0.4167 game seconds / 2.1295 actual seconds, score 0, three lives.
- `ledger.json`: status remains **unknown**, with US$0.27747 conservatively reserved.
  This is neither a confirmed charge nor a claim of zero cost. The original live
  ledger is blocked pending manual usage reconciliation; no additional paid
  request or ledger reset followed.

Frozen manifests identify the source bytes for each attempt. The API attempt
includes the console import fix as an uncommitted source change from a69de3a;
its file hashes, rather than the commit alone, are authoritative. Prompt text,
actual screenshots, issued requests and partial step/action records are retained.
No credentials, auth events or private reasoning are included. The original client
lost the detailed provider event when raising `Terminal response usage missing`,
so a more specific provider cause cannot be established from this record. A later
transport diagnostic fix retains only allowlisted event names, IDs, model/tier,
usage and error codes; it makes no retrospective claim about this failed request.

The previous README demonstration remains a historical development replay.
There is no completed 60-second API video or API performance result from this attempt.
