> **Retained source-harness research record.** This report/protocol describes its original experiment stage. “Current”, “ongoing”, “selected” and acceptance statements below belong to that stage; use the [selected Touhou learning record](../../../../../../docs/touhou-research-record.md) for the released policy, actual API wins and current launcher status. The original report follows unchanged.

# Small visual development set

`visual_devset.py` copies original screenshots unchanged, preserving episode/decision/frame IDs and SHA256 hashes. `cases/*/input.json` is a whitelist of observed frames/held controls/clock, already-returned control schedule and historical delay summaries. `private/*.json` contains human rubrics and historical action audit labels; these are never read by the playing client. No exact entity state, future frame, source future action or current sampled delay is passed to Sol. Human demonstrations can be appended to the separate private label array later.

Build eight selected development cases:

```bash
python -m research.visual_devset build --root /home/ubuntu/wzh/touhou-sol-study --spec research/devset_cases_v1.json --output /tmp/touhou-devset
```

A future frozen run can supply `--delay-profile NEW_PROFILE.json` to give every case the same latest historical control-age summary. Without that option each case retains its source episode's historical profile. Never pass the sampled delay of the current request. The recorded first comparison retained source historical profiles: old real cases may lack the later control-age calibration, so it is a retrospective paired prompt comparison rather than a unified latest-delay benchmark.

```bash
python -m research.visual_devset compare --dataset /tmp/touhou-devset --output /tmp/touhou-case-comparison --suite /home/ubuntu/lzj/coding-agent-suite --candidates grounded_macro tracking_dodge_small tracking_dodge_adaptive --repeats 2 --workers 12 --limit 6
```

The comparison uses native ChatGPT subscription authentication, `gpt-6.1-sol/low`, lean context, fresh ephemeral threads, the same single-action structured schema, and `pixel_controls=true` for all prompts. Case IDs, rubrics and source outcome labels are withheld. The task order is shuffled reproducibly. Variant strategy and latest-frame grounding differ together; results do not isolate one causal mechanism.

`review.html` displays original chronological frames, source IDs, historical delay and all repeated outputs. The first six cases mix real API failures with a simulation win; two additional bomb-grounding/resource cases are available for later comparison. These inspected episodes are development data and must never be called held-out evaluation.

Automatic measures cover legal output, held shoot/focus, bomb requests, duration, planned horizontal displacement using the declared actuator constants, and focused nudges <=35px. These are descriptive, not correctness/safety scores. Current alignment does not imply that staying will be correct after latency and shot flight. Multiple paths and actions may be defensible. Human review must judge grounding, boss drift, delayed bullet threats and the whole maneuver through a gap. No private rollout is implemented; no claim of counterfactual damage, safety or complete episode success is made.

# First paired comparison

Remote artifact: `/home/ubuntu/wzh/touhou-sol-study/visual-devset-v1/`, eight cases and 36 completed subscription decisions across six cases, three prompts and two repeats. All 36 outputs obeyed the frozen action contract.

| Candidate | Focus | Stay | Bomb | Focused nudge <=35px | Median planned horizontal displacement |
| --- | --- | --- | --- | --- | --- |
| grounded_macro | 8/12 | 1/12 | 1/12 | 1/12 | 47.2px |
| tracking_dodge_small | 12/12 | 2/12 | 0/12 | 8/12 | 19.2px |
| tracking_dodge_adaptive | 12/12 | 2/12 | 2/12 | 4/12 | 32px |

The small candidate changed action magnitude as intended. This does not prove better evasion or completion. On `real-phase3-gap`, adaptive repetitions diverged (right18/no bomb versus left28/bomb), requiring visual review. Both new candidates stayed on `sim-track-return` in both repetitions; baseline stayed once and moved right once. All candidates moved right on `sim-aligned-hold`, apparently aiming ahead of boss drift; the case name must not become a stay-only gold label.
