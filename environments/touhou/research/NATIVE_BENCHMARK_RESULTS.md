# Native wrapper randomized paired benchmark

The valid v2 experiment used eight visual devcases, three repeats each, 24 paired blocks and 72 subscription calls, with at most eight concurrent requests. Each arm occupied each randomized position eight times. All arms used the complete unchanged `tracking_dodge_adaptive` task prompt, original PNGs, identical structured schema and `gpt-6.1-sol/low`; no reasoning-zero override or hard output truncation was applied. Only the native wrapper differed. All 72 returned complete legal outputs.

Actual saved `turn/start` RPC text and schema hashes, plus attached-image hashes from client metadata, matched the frozen inputs for all 72 calls. No private labels or entity state were part of those inputs. The post-response coordinate audit used the separately restored source prefix in `private-counterfactual-local-v1.json` only after all calls finished.

| Metric (24 samples/arm) | Default | Existing lean | Aggressive |
| --- | --- | --- | --- |
| Complete return P50 | 11.790s | 12.658s | 13.311s |
| Complete return P95 | 20.967s | 22.193s | 22.169s |
| Input token median | 16299 | 9042 | 7562 |
| Uncached input median | 4011 | 6544.5 | 7562 |
| Aggregate cached input fraction | 70.8% | 27.6% | 5.8% |
| Reasoning token median | 127.5 | 154 | 149 |
| Output token median (including reasoning) | 181.5 | 208 | 203 |

Paired aggressive minus default complete-return differences: median +0.020s, mean +0.400s. Aggressive minus existing lean: median -0.191s, mean -0.098s. The much smaller total context did **not** demonstrate a latency improvement in this experiment. Cache behavior, generation length and shared service load complicate attribution; these are 8-way native subscription measurements, not serial API fastest-latency profiling. Existing default remains the chosen wrapper for subsequent gameplay.

Private coordinate audit in full 640x480 screenshot pixels:

| Euclidean error | Default | Existing lean | Aggressive |
| --- | --- | --- | --- |
| Player P50 | 0.867px | 1.002px | 1.244px |
| Player P95 | 2.857px | 2.706px | 4.314px |
| Boss P50 | 2.695px | 2.155px | 2.339px |
| Boss P95 | 9.978px | 9.127px | 9.130px |

Existing lean reported null for one rendered-present player; its player-error population is 23, separately from this omission. Other player populations are 24. Coordinate errors measure grounding only, not safe movement, damage, generic accuracy or episode success. Small actions are not used as accuracy. The HTML review preserves every repeated answer beside original chronological images for human inspection. Safety and damage remain separate full-episode/private-rollout questions.

## Retained failed first attempt

The first v1 package omitted `native_envelope.py`. Aggressive initialization failed before model turns; lean model turns completed but metadata import failed. No fallback was used. The exact owned runner was stopped, v1 outputs retained, and a preflight import was added before any model requests. V1 contains 32 recorded `turn/start` requests (24 default, 8 lean), 29 `turn/completed` events (21 default, 8 lean), and 3 interrupted/unknown default turns. These extra subscription attempts are reported separately and excluded from the valid paired comparison. Total recorded turn starts including v2 are 104; paid API requests/spend remain zero for this task.

## Artifacts and entry point

Remote valid results: `/home/ubuntu/wzh/touhou-sol-study/native-envelope-ab-v2/results/`.

Local artifact: `/tmp/touhou-native-envelope-ab-v2/results/` contains `summary.json`, `records.json`, `same_input_audit.json`, `private_grounding_audit.json`, actual RPC inputs and `review.html`.

```bash
python -m research.native_benchmark --dataset DATASET --output NEW_OUTPUT --suite SUITE --workers 8 --repeats 3
```

Optional `--private-coordinates REPORT.json` loads private observed labels only after all model responses and writes a separate coordinate audit. Failures and invalid configurations are retained without silent fallback.
