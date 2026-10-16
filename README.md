# SOOOOL — visual policy autoresearch

SOL develops visual game policies through a human-guided research loop: inspect failures, propose prompt changes, evaluate frozen candidates, replay the evidence, and keep the configuration that works. Asterix movement comes directly from the model; each game declares its own control semantics. This repository separates **real-time evaluation** from **simulation development** and records how each result was obtained.

The selected Asterix demo uses **V28, one request at a time, direct unchanged actions, and brief public English decision summaries**. Its historical profile simulation completed 20 game seconds with 500 points and two lives on seed 5. This is one development trial, not a general success rate or real-time API result.

[![Asterix: game and model decision summaries](assets/asterix/preview.png)](assets/asterix/v28-serial-english.mp4)

[Watch/download the replay with original arcade music](assets/asterix/v28-serial-english.mp4) · [How SOL iterated to this policy](docs/asterix-autoresearch.md) · [Evaluation record protocol](docs/evaluation-records.md)

## Run

Linux, Python 3.10–3.12, and a Codex CLI signed in with a ChatGPT subscription supporting the exact model are required. The tested native CLI is 0.162.1. `SOL_CODEX_BIN` selects a standalone executable; `SOL_CODEX_HOME` selects an existing login directory. Credentials are never copied into the repository, and there is no paid API fallback.

```bash
uv sync --locked --python 3.12
codex login
uv run sol doctor --game asterix --auth

# Development: historical delay samples schedule model actions in virtual time.
uv run sol simulate asterix --output runs/asterix-development

# Evaluation: the game clock advances while the model computes.
uv run sol eval asterix --output runs/asterix-realtime

# Explicit comparison without public English summaries.
uv run sol simulate asterix --recipe recipes/asterix-action-only.json

# Append the research decision without overwriting prior assessments.
uv run sol record runs/asterix-development --decision diagnostic \
  --note "Inspect missed pickups; confirm on additional seeds before promotion."
```

Both Asterix modes use 12 raw FPS, a 5× slowdown, and a default 20-game-second horizon. `--seed` and `--duration` select another condition. Simulation pauses the environment when native computation must finish; evaluation uses actual wall time and subscription latency. Subscription latency is not ultrafast API latency. Both send real screenshots/prompts to SOL. `SOL_QUOTA_STOP_PERCENT` defaults to 80; interruptions preserve partial evidence.

## Read the result with its conditions

| Asterix development condition | Action only | Action + English summary |
|---|---|---|
| Eight in-flight requests, direct actions | 400 points; died at 14.67s | 200 points; died at 15.53s |
| One in-flight request, direct actions | 250 points; 20s, one life | **500 points; 20s, two lives** |

These are single seed-5 trials under historical sampled API delays. Serial requests improved observed survival; action-only scoring declined. They motivate the selected recipe, without establishing a causal concurrency effect. The 26-case prompt comparison and these games are different evidence types. [Raw campaign records](artifacts/asterix/) retain failures, source hashes, applied actions and replay checks.

Fresh portable validation completed 20 game seconds at **300 points/one life**, and a five-game-second actual-clock subscription smoke completed at **50 points/three lives**. These new runs are recorded separately from the historical 500-point demonstration.

Every new run snapshots its code/recipe and emits `evaluation-record.json`; `sol record` appends retain/reject/diagnostic decisions. [Validation](docs/validation.md) distinguishes historical records, cold replay, fresh portable simulation, and actual-clock trials. [Real-time evaluation](docs/realtime.md) describes the clocks and remaining API transfer work.

## Racing: SOL develops, then evaluates in real time

[Start with the Racing workflow](docs/racing.md) and [the evidence-linked iteration record](research/racing/EVALUATION.md). SOL changes prompts/control representation, tests delayed closed-loop decisions in simulation, inspects failures, freezes a candidate, and transfers it to continuously advancing API gameplay.

The selected **early lane-commit-v14** checkpoint won seed304 **2:0** using real `gpt-6.1-sol / low / ultrafast` API decisions. The English-summary video variant won a separate **2:1** retake. GPT selects speed, stripe-relative offset and lookahead; a coded 5 Hz visual tracker supplies steering and bend speed limiting. These are hybrid Level 1 results, not direct GPT steering. Historical subscription groups used numeric camera features but omitted image contents; that input limitation is preserved in the record.

```bash
# Use the separate Racing environment/dependencies described in docs/racing.md.
python scripts/racing.py simulate --output runs/racing-dev101 --seed 101
# Real-time eval requires process-only credentials and an explicit capped ledger.
python scripts/racing.py eval --output runs/racing-api304 --seed 304 \
  --budget-ledger runs/racing-budget.json --stage-cap-usd 10
```

[Watch/download: seed304, edited win → loss → win](artifacts/videos/racing-seed304-win-loss-win.mp4). Original heat IDs, clock and score remain visible; actual API explanations and actions stay synchronized. [How to track an evaluation](research/racing/RECORDS.md) defines hypotheses, full cohorts, replay checks, costs and promotion gates. Later development branches are outside this selected lineage.

## Other games

Rhythm and Touhou keep their existing environments, policies and recipes:

```bash
uv run playwright install --with-deps chromium
uv run sol simulate rhythm
uv run sol simulate touhou
```

Rhythm's retained portable simulation scored 50 PERFECT, 1 GREAT, 1 MISS; strict full combo was not met. Touhou's retained portable seed-9 trial ended at 48.82 game seconds with Boss HP 260. These are subscription/profile simulations. Their detailed development and unfinished PingPong research remain preserved independently. Racing retains its selected workflow above.

## Repository map

- `runtime/`: portable subscription transport, CLI, immutable run records and appended assessments.
- `environments/asterix/`: pixels/replay, one shared simulation/evaluation loop, and unchanged model-action delivery.
- `policies/asterix/v28/`, `recipes/`: the selected prompt, output format and exact conditions.
- `profiles/`: historical empirical delay samples with provenance.
- `docs/asterix-autoresearch.md`, `research/asterix/`: the selected research path and scored milestones.
- `artifacts/asterix/`, `assets/asterix/`: public action summaries, replay checks and the selected demonstration.
- [File map](docs/file-map.md), [development workflow](docs/development.md), [observation contract](docs/observation-contract.md), [source/media provenance](docs/provenance.md).

Inactive Asterix candidates, old hop executors and duplicate machine snapshots are available from a fixed historical commit and the optional `codex/evidence` archive. Main carries the focused runnable implementation. See [the research archive](research/asterix/README.md) and [artifact retrieval](artifacts/README.md).

Private repository: https://github.com/sooool-project/sooool. Private access does not grant an additional license to upstream code or media; read the provenance before redistributing them.
