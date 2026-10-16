Freeze paid-calibration inputs from completed subscription runs without any
network/model call:

```sh
python -m research.realtime_profile_fixtures \
  /path/candidate-seed1 /path/candidate-seed5 \
  --output /new/path/candidate-serial-fixtures
```

Default quotas are 21 distinct cohorts: one with one image, one with two images,
and 19 with three images. Source directories are sorted deterministically, then
cohorts are ordered by ID; only race slot zero is selected. All race members must
have identical input hashes and matching native model/effort/schema. Completed
losing episodes are eligible; the builder does not select according to success,
DPS, action quality or future state. Source ordering is explicit and audited.
Duplicate exact transformed-prompt-plus-image inputs are skipped with a recorded
reason, never silently repeated to fill the quotas. If a seed has only 17
three-image cohorts, add another completed seed. Insufficient distinct samples
fail before creating the output directory. A smaller explicitly chosen 15-input
calibration is supported with `--counts 1:1,2:1,3:13`; it has fewer tail samples.

Inputs must be completed empirical-joint subscription simulations with
structured grounded actions, duration limit 48, model `gpt-6.1-sol`, effort `low`,
and frozen target API cap 512. Different candidates or schema configurations
cannot be combined. Model identity, schema, screenshot and prompt hashes are
verified from the issued/decision manifests and actual selected source files.

Only the exact appended paragraphs beginning `Delay condition: entire...`,
`Early-action capacity simulation:...`, and (if enabled) `Artificial latency
stress:...` are removed. Each expected paragraph must occur exactly once; an
unknown/repeated version fails closed. `audit.json` records original byte spans,
removed UTF-8 text, removed byte counts/hashes and original/transformed hashes.
Game policy, observations, visual memory, action format and race/movement gating
remain byte-for-byte. No answer, future outcome, private state or sampled timing
is inserted into the fixtures.

Output includes `fixtures.json` compatible with the existing profiler, copied
original PNGs, `schema.json`, and the source/selection/deletion audit. Run paid
profiling only after freezing and reviewing this output:

```sh
python -m research.profile_api \
  --fixtures /path/candidate-serial-fixtures/fixtures.json \
  --ledger /path/budget.json --output /new/path/candidate-serial.jsonl \
  --samples 1 --general-plan --structured --max-chunks 1 \
  --max-output-tokens 512 --detail high --stage profile
```

Use the exact `max_chunks` recorded in the manifest if it differs from 1.
The existing shared ledger `.profile.lock` prohibits overlapping profiler
processes, and each fixture makes one strictly serial API call. The builder
never handles credentials or sends data; API credentials stay in the profiler's
normal process-memory/getpass path. The fixture's model configuration is an
audited expectation, so matching CLI arguments are required; the existing
profiler does not automatically enforce arbitrary fixture metadata fields.

Historical aggregate latency context embedded in the game prompt is preserved.
After this serial measurement, actual evaluation may replace those aggregate
scalars with the new calibrated delay condition. That is a disclosed prompt
context change, so do not claim this calibration measured byte-identical future
real-time prompts. It measures the recorded task-policy/observation distribution
with exactly the simulator appendices removed, not fresh concurrent API timing.
