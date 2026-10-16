# Latency-aware firing pursuit study, v1

Frozen before collecting new candidate answers. This is prompt/configuration search with a development reward, not weight training. Playing remains gpt-6.1-sol/low seeing original PNGs and allowed public control/timing context; private state is strictly evaluation-only. Existing successful policy is tracking_dodge_adaptive. No engine changes.

## The concrete failure

The successful API episode api-real-human-adaptive-early-v1-seed1 won once at 59.3 logical seconds, but the user identifies a visual/video-time 17–28 second tracking failure. Video/visual and logical clocks differ because original cutins pause physics. Never select this window by logical 17–28 seconds. Public actor inputs must be copied from actual screenshots and source issued observations, with source frame numbers and hashes. Source future actions/outcomes/trajectories are private labels, never prompt content.

The proposed behavioral goal is effective firing during the delayed movement and subsequent waiting period. Moving toward the boss's visible old position is not sufficient. A short safe move may still lose most of the damage window; proximity alone is not the reward.

## Fixed benchmark

Freeze a manifest before model collection. Cover the reported source window, both motion directions and reversals, aligned states, and existing verified human prefixes. Preserve image/control/latency inputs identically across candidates. Compare existing adaptive baseline and at most two new frozen prompt candidates, two independent replies per case, randomized task order, aggressive minimal native outer envelope with the complete task/schema/images retained. Native concurrency at most 12 for case collection. No private state or outcome label enters an actor request.

Fixed delay assumptions are 2.69135 and 3.170205 wall seconds (the previous completed early API episode's observed browser screenshot-to-application P50/P95). These are historical conditions, not current-request known delays or tail guarantees. Replay each verified actual prefix through the observation, retain only already-executing controls during the delay, suppress all future original actions, then apply the returned GPT plan. Score the next 180 logical ticks, with cutin visual frames excluded from logical-time denominators. Report shared pre-action damage/hits separately.

Primary pursuit evidence: actual shot-attributed boss damage over all 180 post-action ticks, shot-damage rate, and longest consecutive eligible firing interval with no shot hit. Also report last-120-tick steady-window damage after a fixed 60-tick in-flight-shot warmup, alignment/range diagnostics, and amount of movement. Warmup does not hide whole-window harm. Bomb-attributed damage must be measured from actual engine events and excluded from shot reward. Do not reward arbitrary movements, exact human key equality, or bombs as pursuit skill. Safety, lives/deaths, bombs, invulnerability, and eligible/terminal lengths are separate explicit measures.

Promotion uses aggregate paired case results, not the single best response: higher shot-attributed damage with no aggregate safety deterioration or increased bomb dependence. Miss-gap improvements support the conclusion; they do not replace damage or safety. If tradeoffs prevent a clear winner, report them and retain the baseline rather than silently changing reward weights. Cases from one run and nearby frames are correlated development evidence, not independent held-out samples.

## Episode checks and paid verification

After case scoring, run the selected candidate and baseline on the same two fixed new development seeds 9 and 10 under calibrated whole-vector historical delays, maintaining request capacity until simulated terminal completion when supported. These become development seeds once inspected. Report win/loss, damage, hits/lives/bombs and pursuit measures on all runs. Do not choose seeds after outcomes. No subscription simulation win is a real API win.

Before a new paid realtime candidate, strictly serial API profile the exact frozen task on recorded actual PNG fixtures; global profiling lock prohibits parallel profiling or live API evaluation during calibration. Profile and later actual API request model/effort/schema/output cap remain explicit. New-prompt delay transport is a labeled model, not fresh measured concurrent performance. Real API validation advances the browser uninterrupted at 1x with no sampled delays, strict early JSON validation, full terminal/usage accounting, clock audit, unchanged engine hash and original browser video. Use default seed1 for comparison; this is an inspected development seed, not held out. One initial new-candidate live trial, then assess before further paid attempts.

Total paid cap remains USD30; verified prior spend USD18.5821818. Missing API credentials block paid phases only; no credential is recovered from chat archives, saved on disk, or passed into subscription workers. All reported live costs come from settled usage, with reservations and unknown charges surfaced.
