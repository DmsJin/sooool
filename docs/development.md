# Reuse the development process

The current policies were developed by changing prompts, visual memory, observation history, control representation, scheduling and executors. No new SOL model weights are included or claimed.

1. Validate the original engine and controller using deterministic tests and replay. Privileged truth belongs only to offline evaluation.
2. Freeze an observation/action contract: exact pixels, public timestamps, history, allowed feedback, and action schema. Keep API and subscription task inputs aligned.
3. Measure the actual workload strictly serially first. Retain failures, tails, raw request timings and usage. Treat concurrency and early-action availability as separate calibration problems.
4. Build a compact, evidence-linked development set from real failure states or human demonstrations. Preserve the original annotations; distinguish acceptable action sets from one mandatory action.
5. Generate prompt/controller candidates and compare on identical states and delay conditions. Retain failed candidates and the gate that selected the winner.
6. Run complete episodes and independent replay. Report development seeds, untouched holdouts, partial prefixes and resumed trajectories separately.
7. Freeze the selected policy before real-time API transfer, and recalibrate when its workload changes.

## Lessons worth carrying forward

- Rhythm: the model must plan beyond response delay. Removing prior latency figures and live RTT caused many literal plans to expire. See `environments/rhythm/experiments/rhythm/LATENCY_PROFILE_ABLATION.md`. Visual calibration memory, acknowledgement history and timestamp semantics are part of the policy.
- Touhou: optimize actual shooting damage and safety over a fixed delayed branch, then check continuous episodes. Case improvements did not guarantee fewer hits. See `environments/touhou/research/TRACKING_BENCHMARK.md` and `TRACKING_RESULTS.md`. Preserve public pixel controls, bomb edge behavior, and readiness/terminal slot handling.
- Asterix: identify the player and useful/harmful sprites first; long held vertical motion and stale replies can undo good decisions. The selected release uses one request at a time and unchanged actions, with no automatic hop or row filtering. Case agreement alone does not establish sustained pursuit or full-episode score; see [the research walkthrough](asterix-autoresearch.md).
- More prompt simplification is not automatically faster or better. Preserve wrapper text and compare with matched inputs. The portable transport is explicitly a new adapter condition.

## Discussions and artifacts

`research/discussions/<game>/conversation.md` is the visible message timeline. `trajectory.jsonl.gz` on the optional evidence branch contains corresponding tool calls/results with call IDs and timestamps. Hidden reasoning and credential-bearing interactive stdin are omitted; secrets are redacted. `manifest.json` records the source hash and export scope. This is an archival export, not new instructions for an agent running the repository.

Each historical/fresh run should be linked to an environment hash, policy version, profile hash, source commit/manifest, execution mode, seed/horizon and scoring definition. Videos must say whether they are wall-clock recordings, capture sequences or deterministic replay renderings. Do not equate a highlight or a fixed action branch with fresh closed-loop model play.

To materialize a discussion tool trace: `uv run python scripts/fetch_artifacts.py research/discussions/rhythm/trajectory.jsonl.gz --fetch`. Omit `--fetch` when the evidence branch is already local.

## Practical policy editing

Copy a recipe rather than overwriting a reference. `sol simulate <game> --recipe <path>` freezes that recipe and snapshots the code and small input files before execution. For Rhythm, change only the explicitly selected memory/policy module, then run the same chart/delay seed for a development comparison. For Touhou, retain the observation/schema/clock contract and select a named candidate in `research/policies.py`; `tracking_benchmark.py` and `tracking_summary.py` provide the original case/gate logic. For Asterix, `research/asterix/evaluation-history.jsonl` records the selected path; exact retired tools and annotations remain in the fixed historical archive. `recipes/asterix.json` and `recipes/asterix-v28.json` select serial V28 with public English summaries; `asterix-action-only.json` is the explicit comparison. Use `sol eval asterix` for the actual clock and follow [the append-only evaluation record protocol](evaluation-records.md). Historical latency calibration is not a current-prompt API validation.

Do not call these fixed-state or development-seed comparisons held-out evaluation. Recalibrate workload latency before claiming real API transfer; preserve the prior profile separately for comparison.
