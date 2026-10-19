# Autoresearch summaries

The README demos came out of Goal mode research sessions: a human supplied the goal, environment, constraints and feedback, and Codex worked through experiments and revisions. These summaries trace the hypotheses, failed attempts, comparisons and selected configurations. Each game retains its own timing and control conditions.

| Game | Read the research | What to look for |
|---|---|---|
| Asterix | [Autoresearch summary](asterix-autoresearch.md) | Visual-policy iterations, human annotations, direct-action execution, serial versus concurrent requests, and public decision summaries. |
| Touhou | [Research summary](touhou-research-record.md) | Human feedback, the selected early checkpoint, development gates and real-time boss-defeat evidence. |
| Racing | [Iteration and evaluation summary](../research/racing/EVALUATION.md) | Selected GPT-guided strategy: 7/7 recorded wins versus 3/7 fixed grid-aware wins on the same seeds; six subscription/profile runs and one real-time API run. |
| Rhythm | [Selected v21 case study](rhythm-autoresearch.md) | Current model-owned absolute tap times, calibration, and the 17s native API result: 24 Perfect / 1 Great / 0 Miss, with two empty presses. |
| Badminton | [Setup and evaluation records](badminton.md) | Tactical goals, native mechanics, GPU simulation and real-time API validation. |
| PCBA test cell | [Research summary](pcba-research.md) | Literal robot commands from vision under modeled delays: placement, interception, throughput cycle and model-timed starts; best simulation 4/5 sorted (3 on time). |
| PingPong | [Tactical control and evidence](tabletennis.md) | Four-worker 1x actual API decisions over asynchronous native planning; seed 11 won 5:1, seed 12 lost 3:5. Earlier S=10 direct-action records remain historical. |

For the common run-record format, see [evaluation records](evaluation-records.md). Recorded simulation results, live API results and replay checks are distinct evidence types.

## Rhythm: selected v21 route

[Case study](rhythm-autoresearch.md) · [Commands](rhythm.md) · [Machine-readable history](../research/rhythm/evaluation-history.jsonl). New literal-time model decisions in subscription simulation, serial API latency profiling, clock alignment audits and one real17s2.5s-approach episode:24 Perfect,1 Great,zero Miss,two empty presses. Human feedback and changed environment conditions are explicit.
