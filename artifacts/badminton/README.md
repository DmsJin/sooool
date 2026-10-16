# Badminton tactical-v1 validation

[GPU validation](gpu-validation-20261017.json) records the local port over SOOOOL
base `dc4eae7` and the original `source_tactical_005` checkpoint. The external
environment is pinned to `da1f787f775ea6524d698c0b063157ded4c0fef9`.
[Historical development totals](historical-tactical-003.json) remain separate.

Validation used an RTX PRO 6000 Blackwell GPU, Python 3.11.17 and MuJoCo 3.3.7.
The protocol was L1/S2, 100 Hz physics, up to 10 Hz public observations, seed 101,
and two fresh 60-game-second windows. Rendering and local decision costs remained
charged. Subscription Fast was disabled. The retained 100-call API Ultrafast
profile supplied virtual delays; no new paid API calls were made.

| Fresh window | Score, ours:opponent | Legal returns | Actual model generations |
|---|---:|---:|---:|
| Rule reference | 3:1 | 18/19 | 0 |
| SOL with profile | 0:6 | 16/22 | 47 |

Both native replays matched. SOL supplied 40 accepted intentions, changing 12
rally choices and 23 recoveries. Both windows had zero invalid actions and zero
timing rejections. This verifies functional transfer and sustained legal play.
The SOL window scored below the reference. These windows do not establish a
full-match win rate or a SOL advantage.

Two original 60-second traces also replayed exactly: rules 3:5 and SOL 2:8.
They used saved actions and made zero model calls. One earlier native preflight
attempt rejected the default-tier `null` echo before generation. Its partial
record is retained and excluded from the scored pair.

The full repository suite passed 44 tests under Python 3.12. The GPU runtime
passed 21 relevant tests and 16 subtests under Python 3.11. Existing Touhou code
requires Python 3.12 syntax and was left unchanged.

The local [video report](../../runs/badminton-validation/gpu/index.html) and raw
evidence are in ignored `runs/`. Each fresh run retains its actual source
snapshot. Full original camera images and transport records remain on the GPU
server at `/home/ubuntu/auto-research/lxy/outputs/sooool_badminton_port_001`.
No policy was promoted.
