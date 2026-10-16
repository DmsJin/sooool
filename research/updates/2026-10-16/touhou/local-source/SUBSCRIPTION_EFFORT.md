# Optional subscription reasoning effort

Existing calls default to `low`. `SubscriptionClient(..., effort='medium')` and
`visual_devset compare --effort medium` select the alternative. An episode JSON
may use `"provider":"subscription", "effort":"medium"`. API episodes reject
every non-low effort before starting work because the paid API path is still low.

For interleaved arms, `--effort-by-candidate` accepts a literal JSON object:

```sh
python3 -m research.visual_devset compare \
  --dataset /absolute/dataset --output /absolute/new-output --suite /absolute/suite \
  --candidates tracking_dodge_safe_intercept_v2 tracking_dodge_safe_intercept_medium_v11 \
  --effort-by-candidate '{"tracking_dodge_safe_intercept_medium_v11":"medium"}'
```

Keys must name selected candidates and values must be `low` or `medium`; invalid
maps fail before output creation or native startup. A worker caches clients by
both schema and effort, preventing cross-arm process reuse. Candidate aliases
are labels only: they do not change the game task or implicitly select effort.

The transport pins `model_reasoning_effort`, checks `config/read`, validates each
fresh native thread's actual `reasoningEffort`, and passes effort on `turn/start`.
Missing or mismatched values fail closed. `effective_native.json` contains only
whitelisted model/auth-mode/config values, never credentials. Every response
records requested effort, effective config effort and actual native thread effort;
the comparer verifies these before admitting a result. `results.json` records the
per-candidate map and uses `effort: mixed` when the arms differ.

The official [configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
documents `model_reasoning_effort`; supported levels depend on the model/client.
This implementation does not claim account availability or quality/latency gains:
only protocol fixtures and unit tests ran. No model or API requests were made.
Sandbox restrictions, aggressive envelope instructions, actor prompts, action
schemas, original game mechanics and rewards remain unchanged.
