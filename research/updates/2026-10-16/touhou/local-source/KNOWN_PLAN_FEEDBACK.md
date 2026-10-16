# Opt-in known-plan feedback

Set `known_plan_feedback: true`, `decision_fanout: 1`, `wait_for_winner: true`, `wait_for_move: false`, `rolling_observations: false`. Invalid combinations fail before creating the episode directory or clients. Default/off prompts remain byte identical to 9b54922 (three frozen regression hashes).

The existing winner gate remains unchanged: a new request can start while the last returned plan is executing, but it cannot start while the latest observation still awaits a legal/invalid answer. Current-plan movement and later queued chunks can continue during response latency; the new answer replaces their unfinished suffix. Death/respawn, boundaries and cinematic freezes still affect position/clock. The controller does not predict positions, repair plans, select routes or trigger bombs.

Opt-in prompt context whitelists the atomic capture clock's logical frame (`frame`), `visual_frame`, `held`, `remaining`, `active_plan` and entire `pending_plan` suffix. It uses capture.active_plan even when the caller's legacy known_plan argument differs. Missing/inconsistent metadata fails closed; it never fabricates an empty queue. No entity state is exposed. Chunk2/4 are supported by existing schema/parser/executor limits; this change only makes the previously returned controls visible in full.

Explicit opt-in wording changes: remove the generic `Pending answers are unknown.` sentence, add the K1 known-plan protocol and captured schedule, and rename `Modeled rolling-pipeline delay` to `Modeled per-request delay` only for the historical independent K1 serial-terminal profile. All profile numbers, assumptions and files remain unchanged; defaults retain the old exact wording. This profile is a modeled condition, not newly measured concurrent or end-to-end API latency. New chunk lengths/prompt overhead need separate validation.

Offline verification: `python3 -m unittest research.tests.test_known_plan_feedback research.tests.test_rolling_protocol research.tests.test_scheduler research.tests.test_control_age_prompt research.tests.test_winner_gating research.tests.test_observation_history research.tests.test_subscription_effort research.tests.test_early_delivery`. No model/API/browser/service needed. Gate tests call the same extracted function as runner with VirtualScheduler to verify movement overlap, blocking of a second unknown answer, and invalid completion. Scheduler, engine, rewards and action execution are unchanged.

This commit is preparation only: no model/API calls, no service start and no experiment results.
