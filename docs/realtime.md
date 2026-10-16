# Actual realtime API evaluation

The selected Touhou path is implemented in the portable CLI. Offline/browser contracts are checked; a fresh paid full-game run of this entrypoint is pending at the user’s request. Historical source-harness API wins are retained separately.

```bash
uv run sol eval touhou --seed 1 --budget-usd 5 --max-calls 100 \
  --output runs/touhou-api-001
```

The default recipe uses `gpt-6.1-sol / low`, actual API streaming, a four-way first-complete-legal race, four in-flight slots, three past screenshots, native English public summaries and the original 1× game engine. Every selected key and duration comes from GPT. The game advances throughout inference. `--budget-usd` is required; an existing shared ledger must be explicitly selected with `--ledger` and counts toward that cumulative cap.

`sol simulate touhou` uses a ChatGPT subscription and modeled profile timing. It rejects API recipes rather than falling back to a paid provider. `sol profile touhou --episode RUN/episode ...` makes strictly serial API requests on deduplicated frozen inputs; returned actions are not executed. These commands measure different conditions.

Real-time acceptance requires boss defeat, completed terminal accounting, actual 1× clock evidence and no pause/blur. `record.json`, the manifest, immutable inputs, responses, applied-action log, evaluator-only final state and original live video form the evidence chain. [Record requirements](evaluation-records.md) describe how to append outcomes without erasing failures. [The case study](touhou-research-record.md) distinguishes historical source-harness runs from new portable CLI validation.

An early legal JSON response can be applied while its terminal event is pending. This does not free its concurrency slot or fee reservation. All losing/stale responses must drain, validate and settle. Missing usage or unknown cost blocks new admission until reconciliation. Readiness/terminal/transport times are distinct; TTFT is not action latency.

The current policy accepts only short public summaries, not internal reasoning traces. A summary and action are displayed atomically from the same selected response. The display panel is outside the actor's observation. Postprocessed videos must retain their original timing and label added audio or rendering changes.

Other environments retain separate research entrypoints: Rhythm's model-owned timing is under `environments/rhythm/experiments/rhythm/model_native.py`; its older cropped-coordinate controller is different. Asterix V28 currently uses the portable profile simulation launcher; a direct-API driver for it is not validated. No universal realtime success claim is made for these other games.

## Racing

Racing retains its separate selected-policy path: `python scripts/racing.py eval` (or `sol eval racing`) uses real API decisions while original-speed physics advances. It requires an existing capped ledger and a process-only credential. See [Racing setup, profiling and evaluation](racing.md). The selected historical seed304 result is verified; migration checks make no new paid success claim.
