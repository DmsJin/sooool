# PCBA test cell: research summary

Goal-mode research with a human setting goals and constraints and a coding agent running
experiments. The model under test is GPT-6.1 Sol at low effort, used as a visual robot
policy that writes every literal command. Metrics, the task flow and the video are in the
[README section](../README.md#pcba-test-cell-belt-to-magazine); per-run records are in
[`artifacts/pcba/simulations.json`](../artifacts/pcba/simulations.json) and
[`artifacts/pcba/evaluations.json`](../artifacts/pcba/evaluations.json).

## Human decisions that shaped the work

| Date | Decision | Effect |
|---|---|---|
| 2026-10-15 | Use the Fast tier after Ultrafast could not be confirmed by the native thread | Live runs are Fast; the simulator uses a modeled ultrafast profile, labelled as such |
| 2026-10-17 | Keep the strict baseline: the model emits every literal action; no hybrid or tactical controller | All protocol work is prompt text and output format; the executor only validates |
| 2026-10-17 | Approve the belt model fix (boards stalled on segment seams and rear-ended each other) | Runs before the fix are not comparable with later ones |
| 2026-10-18 | Goal: all five boards tested and sorted as early as possible; keep five boards | Throughput protocols (lean5–lean7) |
| 2026-10-19 | Target about 20 s per board | Model-timed starts (`start_at_s`) for predictive interception |

## Path

1. **Stopped line, live Fast (`pcba-policy-fast-v1`).** 5 tested, 4 sorted in 600 s with
   5.66 s median latency. The line and fixture wait for the model, so latency only costs
   throughput. Kept as the easy baseline.
2. **Recirculating belt.** Boards circulate on a racetrack and return on the next lap;
   150 s batch deadline, four unpicked laps per board. A scripted oracle (private poses,
   not model evidence) sorts 5/5, so the task is physically feasible.
3. **Latency tuning, live Fast on the loop.** Request latency fell from 10.7 s to 6.8 s
   (prestarted threads, a 0.022 m step margin that stopped replies being rejected for
   landing just over the 0.025 m limit, and a public top-camera pixel-to-world mapping that
   halved reasoning tokens). Boards were picked but none sorted; placement precision became
   the limit.
4. **Simulator.** `sol simulate pcba` keeps fresh model decisions but advances physics on a
   virtual clock using a delay profile, so protocols can be compared under the same delays.
   The PCBA profile is modeled (mean 3.87 s), about 40% faster than measured Fast.
5. **Placement (lean3) and interception (lean4).** Measure the grasp in the wrist image,
   correct on the locator pins, release in its own command; ambush boards downstream
   instead of chasing. First catches moved from 30–113 s to 19–32 s. Boards caught with
   the USB connector reversed could not be seated, so an orientation rule was added.
6. **Throughput cycle (lean5).** Chain seat, release, clamp, test, open and regrasp into
   long guarded chunks, and hold before every release because the arm trails full-speed
   commands by centimetres. Correct sorts across three runs went from 0 to 10.
7. **Timed starts (lean7).** The model may set `start_at_s`; the executor holds until then
   and drops replies that arrive late. Best run: 5 picked, 4 tested, 4 correctly sorted,
   3 by the deadline (`pcba-sim-belt2-timed-v2-s0-ls0`, the showcase video).

## Rejected or not adopted

- Lower image resolution: raised reasoning tokens.
- Concurrency 4 on the live loop: more stale branches, no lower latency.
- lean6 (two replies per board): fewer correct sorts than lean5.
- lean5 without the release hold: 0 correct sorts in three runs.

## Open problems

- No run has sorted all five boards by 150 s; about 35–40 s per board remains.
- The model used timed starts in only 6 of 36 chunks of the best run; short check replies
  at the fixture hover dominate the remaining time.
- Reaching about 20 s per board likely needs longer verified open-loop chunks with
  mid-chunk guards, or an explicitly labelled hybrid skill layer, which would be a
  different experiment from the strict baseline.
- Simulation results are optimistic relative to today's Fast tier; a live run of lean7 on
  the loop has not been made.

## Evidence boundaries

Simulations are development evidence on a virtual clock, not live, realtime or 1x results.
Cohorts are three runs; nothing here is a success-rate estimate. Suction is an ideal
proximity weld, electrical tests are mock device events, and the belt is an idealised
surface model. The showcase video's factory dressing is render-only; the model's cameras
used the plain research scene.
