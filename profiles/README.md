# Profile inventory

Default simulation recipes select one exact profile each; older profiles are archived separately for development provenance.

| Default | Raw representation | Sampling and clock |
|---|---|---|
| Rhythm `native-v17-joint-profile.json` | 179 completed `(api_rtt_s, frame_age_s, transport_overhead_s)` rows | Whole-row empirical resampling; continuous virtual seconds; sampled future delays hidden |
| Touhou `profile-control-early-study-v1.json` | 19 four-candidate joint readiness/terminal cohorts and image-count strata | Whole-vector resampling, at 60 visual-clock frames/s; terminal slots remain occupied |
| Asterix `latency_5x_empirical.json` | 596 capture-to-complete delays with source file hashes | Empirical IID, `ceil(seconds × 12)` raw frames at 5× slowdown; long tails retained |

Asterix's earlier 1/8-speed `sol-ultrafast-v*` directories include `profile.json`, fitted quantile distribution and temporal burst companions. Their original interpolated inverse-CDF sampler is retained under `vendor/`; they are not silently selected for V28 5× simulation.

Touhou's newer `profile-control-tracking-safe-intercept-v2-transport-v1.json` transports serial legal-action marginals into historical race timing. It is included as a modeled profile with its declared limitations, rather than substituted into the older simulation recipe that produced the reference comparisons.

`artifacts/calibration-inputs.tar.gz` contains Rhythm's raw native-v17 request source and Touhou's tracking serial inputs/measurements. Asterix's original 596 source requests are included in `artifacts/asterix-calibration-requests.tar.gz`; both source file hashes were checked against the empirical profile. No fresh API latency measurement is implied by these exports.
