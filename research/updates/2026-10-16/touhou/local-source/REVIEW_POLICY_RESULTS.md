# Reviewed policy iteration results

Human E01–E10 annotations were preserved; D01–D08 received explicitly marked
assistant annotations. The game reward, engine, Gym and executor remain unchanged.
The default validated policy remains tracking_dodge_safe_intercept_v2.

Three development rounds tested shorter visual/corridor prompts, then froze
tracking_dodge_visual_v5 for four fresh repeats. All calls used native subscription
(gpt-6.1-sol/low, aggressive outer envelope, 12 workers), full game task and the
same structured action contract. No actor tools or hidden evaluator labels.

620 native calls completed with legal JSON. 48 initial instantaneous calls were
superseded due incorrect latency-provenance wording. 572 answers yielded 968
correlated private replays; these are not independent model samples. All16 sampled
private clones matched the original browser research replay. No paid API calls.

Frozen confirmation (development fixtures, not held out):

| Condition / metric | Baseline | Frozen v5 |
|---|---:|---:|
| Instantaneous hits, 32 rollouts each | 9 | 3 |
| Instantaneous gross Bombs | 1 | 0 |
| Delayed feasible hits, 104 rollouts each | 12 | 31 |
| Delayed feasible gross Bombs | 38 | 14 |
| Delayed mean ordinary shot damage | 49.71 | 44.38 |
| Delayed E-only hits,64 full windows each | 6 | 13 |
| Delayed E-only mean ordinary shot damage | 64.14 | 59.06 |

Early kills truncate D windows, so raw ordinary damage is not accuracy or DPS.
E-only windows all lasted180 logical ticks without early termination; regression
there remains independently visible. Pre-action losses are separately reported
and excluded from the current action's failure count.

No candidate passed the frozen combined safety/contact gate. None was promoted;
no paid realtime validation was launched. This task added $0 API expense, leaving
the earlier cumulative ledger at $21.6291402 of the user's $30 cap. Subscription
full-return times varied and do not establish an API latency improvement.

Artifacts and complete Chinese report:
/home/zihan/.codex/visualizations/2026/10/15/01a13e38-8ae9-7c13-8e41-d214caeb01a5/kaguya-prompt-v3/REPORT.md

See REVIEW_POLICY_PROTOCOL.md for observation, evaluation and runtime boundaries.
