# SOL realtime games

Run frozen visual `gpt-6.1-sol / low` policies with measured API latency profiles. This repository includes Rhythm (DFJK), Touhou/Kaguya, and Atari Asterix. PingPong and Racing source snapshots are preserved under `research/in-progress/`; they remain outside this portable validation release.

Large archives and videos live on the optional `codex/evidence` branch of this same repository. `main` contains everything needed to run simulations. Use a shallow clone of `main` for the smallest download; materialize selected evidence only when needed.

## Today’s research checkpoint

The [2026-10-16 update](docs/update-2026-10-16.md) adds Rhythm v21/streaming, Touhou feedback studies, Asterix food-sequence candidates, and PingPong/Racing direct-action research. Sources, profiles, selected summaries and redacted discussions are preserved; large records/videos remain optional. Asterix selects V28; the other default recipes retain their previous configurations.

## Start with profile simulation

Requirements: Linux, Python 3.10–3.12, a Chromium-compatible system, and Codex CLI signed in with a ChatGPT subscription that can run the exact model. The environment and model do not need to run on the original experiment server.

```bash
uv sync --locked --python 3.12
uv run playwright install --with-deps chromium
codex login
uv run sol doctor --auth
uv run sol simulate rhythm
uv run sol simulate touhou
uv run sol simulate asterix
```

These simulations send actual game screenshots/prompts to the subscription model. There is no paid API fallback. The model's actual computation time is recorded separately: the virtual environment waits at a scheduled delivery event, without advancing game time during that wait. Scores from this mode are **not real-time API acceptance**.

The tested native executable is `codex-cli 0.162.1`; model/schema/config behavior on other CLI versions needs rechecking. `SOL_CODEX_BIN` can select a native Codex executable when the desktop-managed proxy does not provide standalone app-server stdio. `SOL_CODEX_HOME` selects an existing login directory; credentials are never copied into the repository. `SOL_QUOTA_STOP_PERCENT` defaults to 80 and stops before a new turn at that usage. An interrupted episode remains interrupted, rather than being scored as a loss.

Output goes to a new `runs/<game>-<timestamp>/` directory containing source hashes, exact recipe, model inputs/outputs, timing draws, executed actions and summary. Exit status reports execution integrity; game success is recorded separately in `passed`, `won`, or the score/horizon fields. `--output`, `--seed` select an explicit run directory and seed. Asterix `--duration` sets its raw game-time horizon; Rhythm `--duration` is a partial timing diagnostic and does not meet full-chart acceptance. Full default episodes are recommended.

The Rhythm and Touhou Gym packages are installed from this workspace by `uv sync`. Touhou’s Python Gym bridge additionally needs Node.js; the browser-based simulation does not. Asterix uses the installed ALE/Gymnasium environment.

## Fresh portable validation

| Game | Result from this package |
|---|---|
| Rhythm | Complete 30s: 50 PERFECT, 1 GREAT, 1 MISS; zero provider errors; strict full combo not met |
| Touhou | Complete loss at 48.82 game seconds, Boss HP 260; zero invalid actions; stable wins not reproduced |
| Asterix V28/Hop3 | Historical development: seeds 2/5/6 completed 20 game seconds, scores 500/550/550, three lives each; longer default-recipe validation pending |

These are individual subscription/profile simulations, not new paid real-time API acceptance. Retained evidence, migration attempts and replay videos are indexed in `artifacts/`. See [validation details](docs/validation.md).

## Frozen configurations

| Game | Policy | Timing | Important limit |
|---|---|---|---|
| Rhythm | v19 lean, literal model-authored timestamps + visual calibration memory | 179 measured joint RTT/frame-age/transport rows; 140ms cadence, 12 slots | 52-note development chart; full combo was not established in historical v19 runs |
| Touhou | `tracking_dodge_safe_intercept_v2` | historical four-candidate readiness/terminal joint cohorts | historical latency from another prompt; development simulation, not newly calibrated concurrent latency |
| Asterix | V28 + atomic HopControllerV3 | 596 empirical capture-to-complete samples, 12 raw FPS (5× slowdown) | default horizon is 3600 raw frames; V28 development evidence covers 1200 frames, not native-speed success |

Asterix V28 is the selected default. Its prompt, system instructions and provenance live under `policies/asterix/v28/`. The explicit `recipes/asterix-v28.json` alias selects the same configuration.

## Where to read

- `recipes/`: the default executable configurations.
- `policies/`: frozen prompt/memory/metadata; game-specific controller implementations remain with their environment.
- `profiles/`: measured samples, fitted CDF companions, historical profiles and provenance.
- `environments/`: original engines, interfaces, runners and research modules, retained to avoid rewriting validated timing behavior.
- `runtime/`: portable subscription transport and unified launch/recording entrypoint.
- `research/discussions/`: exported visible development messages and tool trajectories, redacted; original sources remain untouched.
- `research/asterix/`: candidate development and annotation reports.
- `artifacts/`: historical trajectories/videos and fresh validation evidence, labeled by execution mode.
- [Timing and CDF semantics](docs/timing.md), [development workflow and lessons](docs/development.md), [verification](docs/validation.md), [real-time entrypoints](docs/realtime.md).

The launcher uses a portable app-server transport in place of the original machine-specific suite/bubblewrap wrapper. The gameplay prompt, executor and profile simulation remain versioned. This transport change must be assessed using fresh runs; historical performance is not automatically inherited.

This is a private research package. Private repository access does not grant an additional license to source code or media. See [source/media provenance](docs/provenance.md) before redistributing media or upstream code.

Private repository: https://github.com/sooool-project/sooool. Both `main` and `codex/evidence` are required to preserve the complete indexed release; shallow-clone `main` and fetch individual evidence entries as needed.
