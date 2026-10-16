# Read the core first

Use the root README and recipes as the runnable interface. Original environment/research READMEs retain historical commands and absolute paths for provenance.

| Purpose | Files |
|---|---|
| Portable entrypoint and run manifest | [`runtime/cli.py`](../runtime/cli.py) |
| Native SOL subscription transport | [`runtime/subscription.py`](../runtime/subscription.py) |
| Exact default conditions | [`recipes/`](../recipes/) and [`policies/`](../policies/) |
| Profile semantics and sample sources | [`profiles/README.md`](../profiles/README.md), [`timing.md`](timing.md) |
| Actor/evaluator separation | [`observation-contract.md`](observation-contract.md) |
| Large evidence retrieval and checksums | [`scripts/fetch_artifacts.py`](../scripts/fetch_artifacts.py), [`artifacts/index.jsonl`](../artifacts/index.jsonl) |

## Rhythm

Start with `environments/rhythm/experiments/rhythm/model_joint_training.py` (causal event loop), `model_env.py` (pixels and clocks), `model_lean_policy.py` (exact actor projection), `dist/model-executor.js` (literal timestamp execution), and `policies/rhythm/v19/memory.txt`. `hidden_charts.py` belongs to the trusted evaluator. Older cropped/sparse/model variants are preserved experiment versions; do not mix their acceptance claims.

## Touhou

Start with `environments/touhou/research/run_episode.py`, `scheduler.py`, `policies.py`, `control_delays.py`, and `environment.py`. `tracking_benchmark.py` and `tracking_summary.py` are the original delayed-branch scoring and selection pipeline. `dist/engine.mjs` is the deterministic game; `dist/app.mjs` owns browser presentation and the control bridge. `python/touhou_gym` is the structured Gym API, not the SOL actor input.

## Asterix

Start with `environments/asterix/simulate_5x.py` (12 raw FPS/empirical timing/observation history), `hop_controller_v3.py` (atomic-hop semantics), and `policies/asterix/v28/prompt.txt`. The root launcher supplies the portable native pool; prefer `sol simulate asterix` to historical standalone commands. `research/asterix/development-source/` and the optional development archive preserve candidate evaluation and human annotations. `policies/asterix/v28` contains the selected default.

## Racing

Start with [`racing.md`](racing.md), [`scripts/racing.py`](../scripts/racing.py), [`recipes/racing.json`](../recipes/racing.json), and [`policies/racing/lane-commit-v14`](../policies/racing/lane-commit-v14/). `environments/racing/run.py` owns causal simulation and subscription/API transport; `live.py` owns continuous HTTP evaluation; `lane.py` is the coded visual tracker; `live_explained.py` adds the separately evaluated public-summary output. The iteration record is `research/racing/EVALUATION.md`. External roboolympics supplies the read-only game engine. Duplicate active Racing snapshots have been replaced by redirects.

## Ignore on first pass

Full discussion tool traces, all historical profiles, old transport probes, legacy policy variants and offline case truth are not needed to run a frozen policy. Retained evidence documents the selected policies and subsequent development. PingPong snapshots under `research/in-progress` are unfinished source records. Racing uses the selected workflow linked above.
