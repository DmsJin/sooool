# Package validation

Validation is being completed in an isolated Ubuntu directory and new Python virtual environment, using only this repository's runtime and assets. The source machine's suite is not required by the launcher; an explicitly selected native Codex executable supplies the existing ChatGPT login.

## Completed cold replays

- Touhou: all 19 applied actions reproduced the exact final engine state of the original 51.05-second API win, with two hits. This is replay of saved API actions, not a new API or policy win.
- Rhythm: all 215 saved capture times and model delivery events were replayed; the exact evaluator state matched (50 PERFECT, 1 GREAT, 1 MISS, 2 empty presses). Screenshot PNG hashes differed on the new browser/machine and are explicitly not claimed identical. The historical summary's legacy `passed` flag does not meet the current strict full-combo criterion.

Reports are retained with validation evidence. The original environment engines and policy logic are unchanged. Portable transport adapter repairs and incomplete attempts are preserved separately.

## Tests

Six package contracts cover fitted inverse-CDF interpolation/reproducibility, clock conversion, readiness versus terminal capacity, immutable shared cohort inputs and full profile inventories. Existing Rhythm joint-timing tests (3), Asterix timing tests (5), HopControllerV3 tests (6), and Touhou engine tests (8) passed. Local doctor reset ALE and launched Chromium; Ubuntu doctor additionally confirmed a ChatGPT subscription login.

## Fresh subscription simulations

The final frozen runs use real `gpt-6.1-sol / low` decisions, with imposed historical profile timing. The final Rhythm run completed 30.001 seconds: 50 PERFECT, 1 GREAT, 1 MISS, one empty press, max combo 33; 203 requests, 191 delivered plans, zero provider errors and zero transaction rejections. It matches the historical score of 50,700 but does not meet strict full-combo acceptance.

The final Touhou seed-9 run completed as a game loss at 48.8167 game seconds: three hits, no lives/bombs remaining, Boss HP 260; 68 model requests, 16 applied plans, zero invalid actions. This single fresh run does not reproduce the prior development win and does not establish stable success. The failure evidence is retained. Earlier adapter attempts include another loss and are labeled migration diagnostics, not additional fixed-condition trials.


A shallow clone of the committed source branch was installed in another fresh Python 3.12 virtual environment and passed doctor plus all six package contracts without fetching the evidence branch. The default tracked source/assets are approximately 16 MB.

The original Rhythm and Touhou Gym packages are now installed through the root uv workspace. Their Gym API checkers, registered environment creation and complete environment episodes passed; those checks use no SOL policy and are not performance evidence.

All fresh evaluations used historical profile simulation and real subscription decisions. No new paid API evaluation was run. The frozen policies were not retuned to hide losses.

## Selected Asterix policy

The default is V28 with HopControllerV3. Development runs on seeds 2/5/6 completed 20 game seconds at 5× slowdown, scoring 500/550/550 with three lives each. These historical runs do not establish a 60-second result or a fresh result for the packaged default profile. The default profile remains a historical empirical latency condition, not a measurement of V28.
