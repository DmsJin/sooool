# Track evaluation records

A result is useful when its input, condition, complete outcome and accounting can be checked. The selected Touhou case keeps historical records under `artifacts/touhou/` and writes a new `record.json` for every portable simulation or API episode.

## Run and register

```bash
# Real subscription answers; imposed API-like timing, not realtime acceptance.
uv run sol simulate touhou --seed 9 --output runs/touhou-dev-001

# Actual continuously advancing 1x game; explicit budget and process-only key.
uv run sol eval touhou --seed 1 --budget-usd 5 --max-calls 100 \
  --output runs/touhou-api-001

# Idempotent append. A changed record with the same ID is rejected.
uv run sol record runs/touhou-api-001 \
  --registry artifacts/touhou/evaluations.jsonl
```

The API command reads `OPENAI_API_KEY` from process memory or prompts without echo. There is no `--api-key` argument and no credential in snapshots. By default each API run has its own ledger and the stated budget applies to that ledger. `--ledger /path/to/shared-ledger.json --budget-usd N` explicitly makes N a **cumulative ledger cap**, not an additional allowance. Existing committed/inflight/unknown amounts count. Unknown usage stops admission until reconciled; do not erase the ledger or retry around it. Game failure does not cancel billing for losing or late responses.

Budget admission reserves conservative maximum fees for every in-flight request and settles actual usage afterward. The number of requests and the number of actions differ: a four-way race pays for all candidates but executes at most one response for that observation.

## Record contract

| Field | Meaning |
|---|---|
| `record_id` | Stable run identity; default is the unique output directory name |
| `provenance` | `historical_source_harness`, `previous_portable_release`, or fresh `package_cli` |
| `execution_mode` | Actual API, subscription/profile simulation, or saved-action replay |
| `policy_sha256`, `engine_sha256`, `source_commit` | Condition identity; the run manifest retains full file hashes |
| `seed`, `fanout`, summary language | Development/evaluation setup; include seen/held-out context in the note |
| `complete`, `integrity_verified`, `status` | A game loss differs from interrupted transport or incomplete accounting |
| `won`, `passed` | `won` describes boss defeat. `passed` additionally requires valid, continuous 1× API execution and completed accounting |
| `calls_issued`, `actions_applied` | All submitted decisions versus actually installed model plans |
| `latency` | Actual screenshot→action samples for realtime API only; not subscription wall time or simulated timing |
| `accounting` | Billed calls, settled costs, cumulative ledger commitment and unknown-usage state |
| `evidence` | Relative links to manifest, frozen requests, public responses, installed actions and original video |

`survived` with positive boss HP is not a defeat. A simulated win is not real-time acceptance. Replaying saved actions makes zero model calls and is labeled replay. An interrupted run is not silently scored as a game loss. Do not drop a complete failed run or replace old loss evidence with a successful video.

## Inspect a case

`episode/issued.jsonl` records each observation, image hashes and prompt hash. Each `decision_*` directory retains the exact PNGs, prompt and public JSON output. `episode/actions.jsonl` records the selected response, actual application clocks, keys, duration and same-response public summary. `episode/decisions.jsonl` includes stale/losing responses and their costs. `episode/final_state.json` is evaluator-only truth for offline replay; it is never given to the actor.

For the displayed summaries, verify that `brief` and `plan` match the same selected response. For timing, use `capture_to_apply_s` from actually applied actions; do not replace it with TTFT or average all race candidates. For acceptance, require 1× clock evidence, no pause/blur, terminal accounting, no unknown usage and `won=true`.

To publish a compact case, retain its audit and source hashes, put larger inputs/videos on the private evidence branch, and add a checksummed artifact entry. Keep original live capture separate from deterministic replay or a font-corrected re-render. Disclose postproduction such as adding BGM; the public summary is not an internal thought trace. The append operation preserves records; it does not audit arbitrary imported claims for you.
