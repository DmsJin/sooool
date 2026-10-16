# Package validation

Validation is being completed in an isolated Ubuntu directory and new Python virtual environment, using only this repository's runtime and assets. The source machine's suite is not required by the launcher; an explicitly selected native Codex executable supplies the existing ChatGPT login.

## Completed cold replays

- Touhou: all 19 applied actions reproduced the exact final engine state of the original 51.05-second API win, with two hits. This is replay of saved API actions, not a new API or policy win.
- Rhythm: all 215 saved capture times and model delivery events were replayed; the exact evaluator state matched (50 PERFECT, 1 GREAT, 1 MISS, 2 empty presses). Screenshot PNG hashes differed on the new browser/machine and are explicitly not claimed identical. The historical summary's legacy `passed` flag does not meet the current strict full-combo criterion.

Reports are retained with validation evidence. Those earlier Rhythm/Touhou records retain their original engines and policies. The selected Asterix runtime has since changed to direct serial actions; its validation is separate below.

## Tests

Six package contracts cover fitted inverse-CDF interpolation/reproducibility, clock conversion, readiness versus terminal capacity, immutable shared cohort inputs and full profile inventories. Existing Rhythm joint-timing tests (3), Asterix timing tests (5), HopControllerV3 tests (6), and Touhou engine tests (8) passed. Local doctor reset ALE and launched Chromium; Ubuntu doctor additionally confirmed a ChatGPT subscription login.

## Fresh subscription simulations

The final frozen runs use real `gpt-6.1-sol / low` decisions, with imposed historical profile timing. The final Rhythm run completed 30.001 seconds: 50 PERFECT, 1 GREAT, 1 MISS, one empty press, max combo 33; 203 requests, 191 delivered plans, zero provider errors and zero transaction rejections. It matches the historical score of 50,700 but does not meet strict full-combo acceptance.

The final Touhou seed-9 run completed as a game loss at 48.8167 game seconds: three hits, no lives/bombs remaining, Boss HP 260; 68 model requests, 16 applied plans, zero invalid actions. This single fresh run does not reproduce the prior development win and does not establish stable success. The failure evidence is retained. Earlier adapter attempts include another loss and are labeled migration diagnostics, not additional fixed-condition trials.


A shallow clone of the committed source branch was installed in another fresh Python 3.12 virtual environment and passed doctor plus all six package contracts without fetching the evidence branch. The default tracked source/assets are approximately 16 MB.

The original Rhythm and Touhou Gym packages are now installed through the root uv workspace. Their Gym API checkers, registered environment creation and complete environment episodes passed; those checks use no SOL policy and are not performance evidence.

All fresh evaluations used historical profile simulation and real subscription decisions. No new paid API evaluation was run. The frozen policies were not retuned to hide losses.

## Selected Asterix: direct serial V28

The default is V28 with one request, unchanged direct actions and brief public English summaries. Historical seed-5 profile simulation completed 20 game seconds at 500 points/two lives; the action-only comparison scored 250/one life. Both retain raw records under `artifacts/asterix/serial-selected/`. The previous Hop3 three-seed scores are a different execution condition and are not claimed by this release.

The new portable loop passes a whole-trajectory zero-model confirmation using the 44 saved public replies: all 1,200 step actions/rewards/lives and all request screenshot hashes reproduce, at 500 points/two lives. This check ran locally with Python 3.12.3, ALE 0.11.2 and the locked dependencies. It is replay evidence, not a fresh independent performance trial.

The root tests additionally cover an actual-clock loop with a delayed response, no game pause during model waiting, invalid-reply interruption preservation, exact selected task bytes, schema validation and append-only assessment provenance. Real subscription checks are recorded separately under `artifacts/asterix/portable-validation/` as they complete. A short realtime smoke test verifies transport/clock behavior, not 20-second realtime reliability.

The desktop-managed CLI on the local machine timed out at app-server initialization before any model request. The standalone native 0.162.1 executable on the existing Ubuntu experiment host passed subscription authentication. `SOL_CODEX_BIN` must point to a functioning native app-server executable; a matching version string alone is insufficient.

## Fresh selected-policy portable runs

Both commands completed using the standalone native CLI 0.162.1 and real ChatGPT subscription replies. No paid API calls occurred. [Frozen manifests, public outputs and assessments](../artifacts/asterix/portable-validation/) record the exact source; its runtime hashes match immutable commit `0bcfc45`.

| Mode | New model calls | Result | Clock |
|---|---:|---|---|
| Fresh portable simulation, seed 5 | 44 | 20 game seconds, 300 points, one life | Historical sampled API delays; native computation paused outside virtual time |
| Actual-clock subscription smoke, seed 5 | 4 | 5 game seconds, 50 points, three lives | 25.00026 wall seconds; maximum frame lag 4.29ms; three unchanged model actions applied |

The fresh simulation did not reproduce the historical 500-point score. Both use the selected strategy, but the original suite transport and portable app-server are separately recorded conditions, and model decisions are stochastic. The historical replay remains the demonstration; it is not substituted for the fresh trial. The short actual-clock test verifies functional transport and continuous timing, not full-game reliability or ultrafast API latency.

The source host used Python 3.10.22, Gymnasium 0.29.1 and ALE 0.8.1 for these real calls. Local locked-environment replay used Python 3.12.3, Gymnasium 1.2.3 and ALE 0.11.2 and reproduced the selected trajectory exactly. Both successful and interrupted migration checks remain explicitly distinguished. The merged Racing dispatch and subsequent failure-record fixes do not change the successful Asterix action path; their tests remain part of the final branch.
