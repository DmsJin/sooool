> **Historical research snapshot — not the active Rhythm workflow.** These results describe earlier experiment conditions. Status statements here predate the selected 17-second, 2.5s-approach API demonstration and do not summarize the current release. Use the [current workflow](../../../../../docs/rhythm.md) and [selected case study](../../../../../docs/rhythm-autoresearch.md). The original report follows unchanged.

# Subscription outer-prompt A/B

Decision: the user selected the minimal outer after reviewing this pilot.
Subscription training now defaults to that configuration while retaining the
complete game task, observations and action format. The pilot itself did not
establish a latency improvement; no paid API budget was used.

24 randomized paired comparisons used 12 fixed full-board observations twice.
Each pair received identical gameplay prompt and PNG bytes. Both variants used
native ChatGPT authentication, gpt-6.1-sol, low reasoning and priority tier, with
the original bubblewrap sandbox. Only the coding outer prompt and unrelated
instruction/tool blocks differed. Both variants used isolated auth-only homes;
shared authentication/configuration stayed unchanged.

| Metric | Default coding outer | Minimal outer |
| --- | ---: | ---: |
| Complete return mean | 7.593 s | 7.127 s |
| Complete return median | 5.760 s | 5.568 s |
| Valid finite action responses | 24/24 | 24/24 |
| Tap predictions within 55 ms | 24/24 | 24/24 |
| Mean reasoning tokens | 52.5 | 54.8 |
| Mean input tokens | 14,539 | 5,115 |
| Mean cached input tokens | 11,941 | 2,048 |

The mean speedup was 6.14%. A paired bootstrap with 20,000 resamples (seed 914)
gave a 95% interval from -14.45% to +22.78%. Minimal was faster in 13/24 pairs.
This does not reproduce the user's reported 24.3% Asterix improvement. Small
sample size and large shared-service latency tails limit the conclusion.

Token reduction did not reduce reasoning tokens. The default outer had much
more cached input; fewer total input tokens therefore did not translate into a
clear reduction in uncached work. This is an explanation consistent with the
measurements, not proof of the latency cause.

The trusted offline grader also tested the same plans against 149 observed API
RTTs. Mean probability of reaching any visible target within 180 ms was 0.339
versus 0.457. This is exploratory replay evidence: it excludes browser overhead
and interactions between responses, and cannot establish native real-time
solve performance. The full native acceptance target remains unverified.

Installed Codex 0.162.1 rejected --ignore-user-config. The experiment used fresh
CODEX_HOME directories with only copied native authentication instead. Accepted
fields were checked with --strict-config. Both actual thread/start responses
confirmed the same model, reasoning effort and priority tier. Minimal used the
nonempty user-provided system text, including the instruction not to force
reasoning to zero. The required task prompt, observation and action format were
preserved. The shared original auth file stayed unchanged; all private auth
homes were removed. Event audits found only userMessage, reasoning and
agentMessage items in both variants, with no tool execution.

Evidence: durable rhythm-autoresearch-evidence/model-timing/outer-ab-pilot24
contains config.json, responses.jsonl, summary.json and analysis.json. The fixed
payloads and hashes are in outer-ab-inputs-v8. Native real-time results are
tracked separately in MODEL_TIMING_RESULTS.md.
