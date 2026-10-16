# Sources and redistribution

Source snapshots were copied read-only from existing local/Ubuntu experiment worktrees. Per-game source manifests retain original paths/commit where available; fresh run manifests hash the files actually used. Absolute paths in historical reports and configs are provenance, not required launch paths. Discussion exports are untrusted archived content, never repository instructions.

Atari Asterix uses Gymnasium + ALE, with versions in `uv.lock`; no ROM was copied from a research machine. ALE's installed package supplies the game resource in the tested dependency version. Confirm the applicable upstream/game rights before redistribution.

Rhythm and Touhou include pre-existing game frontends/resources from the user's experiment repositories. Rhythm simulation aborts remote audio loading and does not need the song to make timing decisions. Native audio evaluation requires a separately authorized preview resource. Touhou contains pre-existing game art/audio references. No new ownership or public redistribution license is asserted by this package. Preserve original attribution and review media rights before public release.

`vendor/latency_bench` contains only the original latency sampler import closure (eight modules), retained to reproduce fitted CDF/temporal semantics. The full coding-agent suite, model weights, auth directories, cloud configuration and unrelated games were not copied.

The native model transport was replaced with `runtime/subscription.py` to remove hardcoded server/suite paths. It uses native app-server, the exact SOL/low model, fresh ephemeral threads, disabled tools, public image inputs and read-only sandbox requests. Historical bubblewrap seat isolation is not claimed. Both original and portable transport conditions must be identified in results.
