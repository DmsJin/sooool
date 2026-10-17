# PingPong entrypoint validation

Both `sol simulate pingpong` and `sol eval pingpong --source api` completed full
native matches using the PR #12 implementation at
`b2f85f0549b07d7709a59736eac6dd8d52b780bb`. Gameplay, model prompts, native
planning and virtual scheduling are unchanged by the later integration cleanup;
replay labels, profile provenance metadata and regression checks were updated.

| Condition | Subscription simulation | Actual API evaluation |
| --- | --- | --- |
| Seed / level | 11 / L1 | 11 / L1 |
| Clock | Virtual API-profile delivery; may pause for subscription computation | Continuously advancing actual wall time, 1x target |
| Model | Fresh GPT-6.1 Sol Low subscription replies | GPT-6.1 Sol Low / Ultrafast API |
| Workers | 1 subscription worker, 4 virtual slots | 4 actual API workers |
| Score | 5:0 | 5:1 |
| Legal serves / returns | 3/3, 11/11 | 4/4, 6/7 |
| Plans installed / discarded | 26 / 14 | 17 / 8 |
| Completed model calls | 53 subscription | 43 API |
| Accepted replies | 45 | 32 |
| Game / wall seconds | 34.42 / 281.414 | 31.14 / 31.453 |
| Paid API cost | $0 | $1.373703 |

Both CLI processes exited 0, with `native_match_completed=true`, no controller
error and zero invalid model or native actions. Every installed return flight
references an accepted model decision; policy fallback was zero. Simulation
replies and paired terminal boundaries were never delivered early, and private
sampled timing was absent from actor snapshots. These are single-match checks,
not a cross-seed stability or win-rate claim. The earlier seed-12 loss remains
retained in [the evidence index](README.md).

The profile is still the documented 12-call historical direct-action proxy, not
an exact calibration for current tactical prompts or four concurrent API workers.
Simulation's 281-second wall duration is not real-time API acceptance.

## Reproduction and original records

Use [the setup and commands](../../docs/tabletennis.md), Python 3.11, the pinned
read-only RoboOlympics runtime, EGL on allocated GPU 0, `OPENBLAS_NUM_THREADS=1`
and `OMP_NUM_THREADS=1`. The simulation used delay seed 7319, four virtual slots,
0.65-second request interval and the recipe's priority subscription tier. Actual
evaluation used the same interval and a 1x target with four API workers. Both had
two native planning processes and 20 Hz public camera/rule control.

The Codex CLI was 0.162.1, with `SOL_CODEX_BIN` explicitly configured and an
existing ChatGPT login selected through user-authorized `SOL_CODEX_HOME`.
No credentials are included. No subscription-to-API fallback was used.

Machine-readable checks:

- [Subscription simulation](simulation-seed11-validation.json)
- [Actual API evaluation](api-pr12-seed11-validation.json)

Server workspace: `/home/ubuntu/lzj/sooool-pingpong-tactical`.
Complete requests, native poses, planning logs, summaries and source snapshots:

- `runs/tabletennis/subscription-sim-pr12-seed11-001`
- `runs/tabletennis/api-eval-pr12-seed11-001`

The API ledger remained cumulative: $17.6265816 before evaluation and
$19.0002846/$20 afterward, with zero pending reservations. No further paid calls
were made while integrating these results. Earlier zero-plan failures reported by
the PR author remain separate observations; their exact cause is not established
by these successful server runs.
