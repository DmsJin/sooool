> **Retained source-harness research record.** This report/protocol describes its original experiment stage. “Current”, “ongoing”, “selected” and acceptance statements below belong to that stage; use the [selected Touhou learning record](../../../docs/touhou-research-record.md) for the released policy, actual API wins and current launcher status. The original report follows unchanged.

# Human-prefix visual case comparison

Six fixed observations from the recorded human run were evaluated with three unchanged game-task prompts and two repetitions: 36 native subscription calls total, `gpt-6.1-sol/low`, at most eight concurrent. All 36 returned legal one-action outputs. The public bundle contained original historical screenshots, current held keys `[0,1,1,0]`, clock metadata, no pending plan, and historical control-age median/P95 2.17/2.54s. No future human actions or private labels were uploaded. Actual RPC text, schema and attached image hashes matched for every call.

This round had already issued eight calls under the default wrapper when the user requested the aggressive wrapper for future work, so it remained frozen as default throughout. Subsequent newly started subscription rounds should follow the aggressive-wrapper preference; the full game-task prompt and PNGs remain intact.

| Descriptive measure (12 responses/candidate) | grounded_macro | tracking_dodge_small | tracking_dodge_adaptive |
| --- | --- | --- | --- |
| Legal outputs | 12 | 12 | 12 |
| Focus held | 8 | 12 | 12 |
| Stationary | 1 | 2 | 2 |
| Bomb requested | 5 | 4 | 4 |
| Median planned horizontal displacement | 44px | 24px | 34.4px |

On `human-obs-0671`, both new candidates stayed in both repetitions; baseline stayed once and moved left once. On `human-obs-1393` and `human-obs-1788`, all six answers per case requested a bomb. On `human-obs-0929`, baseline repetitions differed (focused right36/no bomb versus normal right18/bomb); both new strategies chose focused right movements without bombs. These are behaviors to inspect, not safety scores. The human's future move is not a unique gold action, and a human without a 2.17s artificial delay solves a different control problem. No complete-game Sol win, damage improvement or safer path is inferred from these static outputs.

Local human review: `/tmp/touhou-human-case-comparison-default-v1/comparison/review.html`.

Local results and provenance audit: `/tmp/touhou-human-case-comparison-default-v1/comparison/{results,public_input_audit}.json`.

Remote public-only run: `/home/ubuntu/wzh/touhou-sol-study/human-visual-devset-v1/` (no `dataset/private` directory). Private review labels were joined only on the local review machine after all model calls finished.
