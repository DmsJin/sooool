# Profile inventory

Badminton uses `badminton/tactical-api-100.json`: the unchanged 100 serial API
Ultrafast samples from `badminton_tactical_003`. Generation mean 2.006s, P95
2.862s. The clock excludes token preflight and local accounting. This historical
profile schedules S2 tactical decisions; subscription simulation itself disables
Fast and does not measure new API latency. See [Badminton](../docs/badminton.md).

Default simulation recipes select one exact profile each; older profiles are archived separately for development provenance.

| Default | Raw representation | Sampling and clock |
|---|---|---|
| Rhythm `native-v17-joint-profile.json` | 179 completed `(api_rtt_s, frame_age_s, transport_overhead_s)` rows | Whole-row empirical resampling; continuous virtual seconds; sampled future delays hidden |
| Touhou `profile-control-early-study-v1.json` | 19 four-candidate joint readiness/terminal cohorts and image-count strata | Whole-vector resampling, at 60 visual-clock frames/s; terminal slots remain occupied |
| Asterix `latency_v16_actual_5x_512cap.json` | 536 valid capture-to-complete delays from the historical V16 API campaign | Empirical IID, `ceil(seconds × 12)` raw frames at 5× slowdown; long tails retained |

Asterix's earlier 1/8-speed `sol-ultrafast-v*` directories include `profile.json`, fitted quantile distribution and temporal burst companions. Their original interpolated inverse-CDF sampler is retained under `vendor/`; they are not silently selected for V28 5× simulation.

Touhou's newer `profile-control-tracking-safe-intercept-v2-transport-v1.json` transports serial legal-action marginals into historical race timing. It is included as a modeled profile with its declared limitations, rather than substituted into the older simulation recipe that produced the reference comparisons.

`artifacts/calibration-inputs.tar.gz` contains Rhythm's raw native-v17 request source and Touhou's tracking serial inputs/measurements. Asterix's original 596 source requests are included in `artifacts/asterix-calibration-requests.tar.gz`; both source file hashes were checked against the empirical profile. No fresh API latency measurement is implied by these exports.

## Racing

`racing/profile.json` and `measurements.jsonl` preserve the 32 strictly serial paid API measurements used for early development. Minimum 0.984s, median 1.350s, P95 2.258s. This measured one-frame direct steering, not the selected two-frame lane-goal workload or concurrent traffic; its use in current simulations is explicitly a historical proxy. `scripts/racing.py profile` measures selected-policy recorded inputs serially and saves a new profile without overwriting this reference. See [Racing](../docs/racing.md).

The selected Asterix serial recipe uses the historical V16 valid-response sample list, with delay RNG seed `91 + game_seed`. It retains long tails and does not model provider failures. `latency_5x_empirical.json` remains the earlier 596-row calibration reference and is not the selected recipe. Native realtime evaluation records actual subscription time instead of sampling this profile.
