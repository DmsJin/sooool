# SOOOOL

**GPT-SOL playing games, frame by frame. The game doesn’t wait.**

SOOOOL is a research loop for getting GPT-SOL to play real-time games. GPT-SOL sees the frames, decides what to do, and sends an action. Then it sees what happened and decides again. The environment keeps moving while the model thinks, so a good decision can arrive too late.

The gameplay decisions come from GPT-SOL on each turn. The surrounding code handles observations, timing and execution, with each game declaring its control setup below.

<table>
<tr>
<td width="50%" align="center"><a href="assets/gameplay/touhou.mp4"><img src="assets/gameplay/touhou.gif" alt="GPT-SOL dodging Kaguya's bullet patterns with live English decision summaries" width="440"></a><br><b>Touhou</b> · Real-time API · 1×</td>
<td width="50%" align="center"><a href="assets/gameplay/racing.mp4"><img src="assets/gameplay/racing.gif" alt="GPT-SOL selecting racing targets through bends and obstacles, with live decisions" width="440"></a><br><b>Racing</b> · Real-time API · Hybrid steering</td>
</tr>
<tr>
<td colspan="2" align="center"><a href="assets/gameplay/asterix.mp4"><img src="assets/gameplay/asterix.gif" alt="GPT-SOL collecting food in Asterix alongside original public decision summaries" width="600"></a><br><b>Asterix</b> · Profile simulation replay · 5× slowdown</td>
</tr>
<tr>
<td width="50%" align="center"><a href="assets/gameplay/rhythm.mp4"><img src="assets/gameplay/rhythm.gif" alt="GPT-SOL hitting DFJK notes and building a perfect combo" height="270"></a><br><b>Rhythm</b> · Real-time API · 1× · Gameplay only</td>
<td width="50%" align="center"><a href="assets/tabletennis/seed11-full.mp4"><img src="assets/gameplay/pingpong.gif" alt="GPT-SOL selecting table-tennis tactics at 1x, with both camera views and original public decision summaries" width="440"></a><br><b>PingPong</b> · Real-time API · 1× · Four tactical workers</td>
</tr>
</table>

You can watch GPT-SOL dodge a screen full of bullets, race a rival, collect food in Atari Asterix, play robot table tennis, or hit notes in time with the music. Then inspect its decisions, change the policy, and send it back into the game.

**Simulated latency. Real model decisions.** During development, cheaper inference drives fresh decisions from actual game frames, with actions delivered under a measured API latency profile. Freeze a candidate, then evaluate it with the real API while the game clock keeps running. The repository includes the environments, prompts, profiles, runners and experiment records for this loop.

## Games

| Game | Job | Demo |
|---|---|---|
| **Touhou / Kaguya** | Dodge bullets. Defeat the boss. | Real-time API at 1×. GPT-SOL chooses movement, shooting, focus, bombs and duration. |
| **Racing** | Find a line. Beat your rival. | Real-time API at 1×. GPT-SOL chooses speed and racing targets; a coded controller supplies steering. |
| **Rhythm** | Hit the right key at the right time. | Native browser/audio API capture at 1×, with DFJK inputs. |
| **PingPong** | Serve, return, win the point. | Real-time API at 1× with four tactical workers. GPT-SOL selects shot placement; a camera-only rule controller serves, tracks and executes. [Setup and results](docs/tabletennis.md). |
| **Badminton** | Place the shot. Recover for the next one. | Tactical goals with native mechanics; real-time API at S3. [Setup and control boundary](docs/badminton.md). |
| **Atari Asterix** | Collect food. Avoid enemies. Stay alive. | Historical delay simulation at 5× slowdown, with model actions applied unchanged. |

The GIFs are continuous excerpts at their source playback speed. PingPong shows both native camera views and public model summaries from a complete actual-clock match; its linked full video retains every point and failure. Racing uses hybrid steering. Touhou, Racing and Asterix also show original public decision summaries. Rhythm currently shows gameplay only. These are selected demonstrations, not win-rate estimates. [Clip sources and cuts](assets/gameplay/README.md).

## How it works

We developed these policies by giving Codex a goal in **Goal mode** and letting it work through trial and error. We supplied the environment, objective, constraints and occasional feedback; Codex ran experiments, inspected failures, proposed changes and tried again. This is the **autoresearch** loop behind the demos.

1. **Set a goal.** Give the agent a game, a target outcome and an experiment budget.
2. **Profile and play.** Measure the target API’s latency, then develop with fresh GPT-SOL decisions under sampled delays.
3. **Try, inspect, revise.** The agent runs episodes, reads trajectories and replays, changes the instructions or permitted control setup, and compares candidates. Human feedback can steer the next experiment.
4. **Freeze and verify.** Select a candidate from the recorded comparisons, freeze its configuration, and test it against the real clock. Keep the failures, timing, costs and outcomes alongside the wins.

Codex runs the research loop; GPT-SOL makes the online gameplay decisions. The demos use selected configurations from that process. Concurrency, game speed and control abstractions are recorded per experiment.

**[Check autoresearch summaries →](docs/autoresearch-summaries.md)**

## Play a round

Start with a development run. You need Linux, Python 3.10–3.12, Chromium-compatible dependencies, and a Codex CLI signed in with a ChatGPT subscription supporting the configured model. The tested native CLI is 0.162.1.

```bash
uv sync --locked --python 3.12
uv run playwright install --with-deps chromium
codex login

uv run sol doctor --game touhou --auth
uv run sol simulate touhou
```

This sends actual game screenshots and prompts to the subscription model and schedules actions using a historical latency profile. Simulation can wait for model computation; scores from this mode are development results. There is no paid API fallback.

To evaluate Touhou against the real clock:

```bash
uv run sol eval touhou \
  --seed 1 \
  --budget-usd 5 \
  --max-calls 100 \
  --output runs/touhou-api-001
```

Real-time Touhou evaluation requires an OpenAI API key, read from process memory or prompted without echo. The game keeps running while requests are in flight. The runner records inputs, public decision summaries, applied actions, timing, video and cost. The retained source-harness demo defeated Kaguya; fresh full-game paid validation of the portable launcher is pending. [Setup, budgets and timing](docs/realtime.md).

Racing and PingPong use separate native dependencies. See the [Racing workflow](docs/racing.md), [PingPong tactical setup](docs/tabletennis.md), [Badminton setup](docs/badminton.md), and [complete release guide](docs/release-guide.md) for their conditions and entrypoints.

## PingPong: tactical control at 1×

GPT-6.1 Sol Low / Ultrafast chooses `safe_center`, `wide_left`, `wide_right` or
`short_center` through four staggered workers. Native physics runs at 100 Hz while
camera tracking and rule control run at 20 Hz; two asynchronous planning workers
prepare strokes without pausing physics or catching up late frames. Serving and
joint control are rule based. This is hierarchical tactical control.

Two complete actual API matches used the same gameplay code and settings:

| Seed | Score | Legal serves | Legal returns |
|---|---|---|---|
| 11 | **5:1** | 4/4 | 6/7 |
| 12 | **3:5** | 3/4 | 5/9 |

The second seed still has missed contacts and an own-half return; stable serving
and long rallies are not solved. The sidebar labels the latest accepted public
summary, its observation time, the `NEXT` policy and the reply actually executing.
Four workers improve reply throughput; individual replies still take about two seconds.

[Watch the complete dual-view match](assets/tabletennis/seed11-full.mp4) ·
[Run rules or the actual API](docs/tabletennis.md) ·
[Both matches and retained evidence](artifacts/tabletennis/README.md).

## Make it play better

The fun part is watching a policy fail, figuring out why, and trying again.

Did it dodge where the bullet was, instead of where it was going? Did it commit to a turn too late? Did a useful explanation delay the action that could have saved it?

Inspect the replay, change the prompt or control representation, evaluate the candidate, and keep the evidence. Freeze a candidate before real-time evaluation. The research records preserve failed attempts alongside the selected policies.

No model weights were trained for the selected Touhou policy. Its behavior was developed through prompts, human feedback and repeated evaluation.

- [Touhou research](docs/touhou-research-record.md): feedback, policy changes and the selected boss-defeat run.
- [Racing experiments](research/racing/EVALUATION.md): candidate policies, full cohorts and transfer to real-time gameplay.
- [Asterix experiments](docs/asterix-autoresearch.md): direct model actions and the selected serial policy.
- [PingPong tactical control](docs/tabletennis.md): asynchronous native planning, four-worker API decisions, dual-view replay and cross-seed failures.
- [Evaluation records](docs/evaluation-records.md): conditions, replays and appended research decisions.

## Code

| Path | Contents |
|---|---|
| `runtime/` | Subscription transport, launchers and run records |
| `environments/` | Game engines, interfaces and game-specific controllers |
| `policies/`, `recipes/` | Prompts, output formats and executable configurations |
| `profiles/` | Measured latency samples and provenance |
| `research/` | Development records, comparisons and retained discussions |
| `artifacts/`, `assets/` | Evidence indexes, videos and README highlights |

[File map](docs/file-map.md) · [Validation](docs/validation.md) · [Timing](docs/timing.md) · [Optional evidence](artifacts/README.md)

Large evidence archives are optional; you can run the source package without downloading them. Public decision summaries are short model-authored outputs, not internal reasoning transcripts. GIFs have no audio; source-video music and editing are documented per artifact.

This is a private research package. Repository access does not grant an additional license to upstream code or media. See [source and media provenance](docs/provenance.md) before redistribution.
