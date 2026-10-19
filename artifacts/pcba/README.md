# PCBA visual-action evaluation record

Current model integration: three environment trials. The earlier scripted 5/5 environment check is separate; no trained robot VLA weights are used.

| Round | Purpose | Model calls completed / attempted | Picked / tested / correctly sorted | Video |
|---|---|---|---|---|
| 1 | 0.5-second observation validity diagnostic | 3 / 3 | 0 / 0 / 0 | [Replay](../../runs/pcba-policy-strict-v1/replay.mp4) / [report](../../runs/pcba-policy-strict-v1/report.json) |
| 2 | Literal action chunks before speed-tier switch; interrupted | 9 / 10 | 1 / 1 / 0 | [Replay](../../runs/pcba-policy-chunks-v1/replay.mp4) / [report](../../runs/pcba-policy-chunks-v1/report.json) |
| 3 | Confirmed Codex Fast; five-board full task attempt | 68 / 69 | 5 / 5 / 4 | [Replay](../../runs/pcba-policy-fast-v1/replay.mp4) / [report](../../runs/pcba-policy-fast-v1/report.json) |

Round 2 was interrupted when the user requested Ultrafast. Local preflights did not confirm that tier; the user then selected Fast. All attempted trials and connection checks remain in runs/.

Replays use original wall timestamps. Rounds 1–2 rendered native camera samples during execution; round 3 rendered its saved native states after execution to reduce interference. Frames are held between samples. Each report retains clock drift/late ticks; no failed timing check is omitted.

Nominal station calibration is public policy input. Dynamic object truth and unreleased test outcomes are not policy inputs. Mock tests, ideal suction and sparse magazines limit transfer claims. One batch does not estimate a success rate.

See [setup and interfaces](../../docs/pcba.md) and [machine-readable results](evaluations.json).

Selected Fast result: 5 boards picked/tested, 4 correctly sorted, zero incorrect sorting or drops; the fifth board remained in the fixture at the wall limit. Median inference 5.66 s; 14 expired chunks and one overlong model chunk were rejected. The task has weak realtime pressure because the line and fixture wait.

## Recirculating belt: subscription simulations

All 26 development simulations on the revised belt (placement, interception, throughput
cycle and model-timed start protocols; three seeds per cohort) are listed with their
discard reasons and report hashes in [simulations.json](simulations.json). They are
virtual-clock development evidence with the modeled ultrafast delay profile, not live
results. The selected run and its showcase video are described in the
[README section](../../README.md#pcba-test-cell-belt-to-magazine).
