# Actor and evaluator boundaries

The default SOL policies operate on the original browser/Atari visuals and permitted public control feedback. They never receive the privileged Gym state or a sampled future response delay.

| Game | Default SOL input | Evaluator / environment-only state |
|---|---|---|
| Rhythm | Actual screenshot PNG, public capture/monotonic clocks, model-authored pending taps, raw execution receipts, historical RTT and calibration memory | Chart notes/seed, future note times, actual judgement truth, future sampled latency calendar |
| Touhou | Canvas/HUD PNGs, public viewport/control protocol, prior own visual estimates and applied plans, historical delay summary | True player/Boss/projectile coordinates, engine internals, future RNG/delays, scoring branches |
| Asterix | Three timestamped 224×224 visual frames, allowed applied-action history, current held action, historical delay summary | ALE internal state, future sprites/RNG, reward/lives used only by offline evaluation, future latency draw |

The original `RhythmEnv` Gym wrapper exposes next-note structured observations, and `KaguyaEnv` exposes structured player/Boss/bullet state for environment research. They are installed for reuse and API compatibility; **these observations are not the screenshot-only SOL benchmark interface**. The portable runners use `ModelVisualEnv`, `BrowserEnv`, and actual ALE camera pixels instead.

The generic controllers implement declared mechanical semantics: literal timestamp forwarding, button edges/chunks, atomic hops, capacity/order/stale-result rules. Calibration and offline scoring may inspect privileged truth. Their results must not be passed into the online actor as hidden-state guidance.

This portable research runtime requests read-only native sandboxing and disables tools; it rejects tool/approval events. It does not claim the original external bubblewrap/official benchmark seat isolation. Evaluation validity and adversarial isolation are separate claims.
