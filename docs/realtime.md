# Real-time evaluation

## Badminton: actual realtime API at S3

`sol eval badminton --budget-usd 15 --ledger outputs/badminton-budget.json --env-file /absolute/path/to/.env --output outputs/badminton-api101`
runs one L1, seed-101 native match. It uses one serial `gpt-6.1-sol / low / ultrafast`
request and a continuously advancing S3 clock. Camera control and native stroke
planning run off the physics process. Limits, preparation timing, public English
summaries and verified replay video are described in [Badminton](badminton.md).
Run `sol preflight badminton` with an explicit output directory before paid use.

## Asterix

```bash
uv run sol eval asterix --seed 5 --duration 20 --output runs/asterix-realtime
```

This uses actual ChatGPT subscription inference and a continuously advancing 12-raw-FPS clock (5× slowdown). One request is in flight; complete model actions are held unchanged until replaced. Game time continues while the model computes. There is no automatic hop release, neutral landing or row-based filtering. A completed response is applied on the next game tick; the next observation is captured at the next four-frame observation tick.

`sol simulate asterix` uses the same policy/action semantics but samples a historical API delay profile and pauses native computation outside virtual game time. The default 500-point demonstration is profile development evidence. The realtime command measures subscription latency and game performance; it is not a paid ultrafast API calibration or native-speed result.

Each trial retains the exact task, model public output, capture frame, delivery frame, actual capture-to-apply duration, frame lag, applied action, rewards/lives, source snapshot and evaluation record. Interrupted calls preserve partial artifacts; authentication failures cannot fall back to paid API. The default quota stop is 80%. Record retain/reject decisions with `sol record`; see [the recording protocol](evaluation-records.md).

A paid ultrafast API trial requires the user's own secure credentials, explicit per-run spending budget, complete-response and early-action calibration, failure/usage accounting, and fresh real-time validation. The original API research utilities remain available at [the fixed Asterix source checkpoint](https://github.com/sooool-project/sooool/tree/053545c1c27e6beccb80598e7a4d57f80865afc1/research/asterix/realtime-source). This release does not expose an unvalidated paid API launcher or inherit an old budget authorization.

## Touhou: actual realtime API evaluation

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

## Other games

Rhythm retains its original real-time research paths:

- Rhythm model-owned timing: `environments/rhythm/experiments/rhythm/model_native.py`; prior cropped-coordinate campaign: `realtime_v2.py`. Native audio evaluation additionally needs the authorized audio resource and continuous audio/browser clocks.

Their original commands retain their declared resource and budget assumptions. The root `sol eval asterix` uses the shared native loop; `sol eval racing` delegates to the selected Racing driver. Historical and fresh results must remain separately labeled.

## Racing

Racing retains its selected-policy path: `python scripts/racing.py eval` or `sol eval racing` uses real API decisions while original-speed physics advances. It requires an existing capped ledger and a process-only credential. See [Racing setup, profiling and evaluation](racing.md). The selected historical seed304 result remains separate from this Asterix release and its subscription checks.

Protocol reference: [OpenAI Docs — Codex app-server](https://learn.chatgpt.com/docs/app-server).
