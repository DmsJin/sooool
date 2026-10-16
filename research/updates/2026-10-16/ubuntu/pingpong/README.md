> **Historical PingPong experiment.** This snapshot spans earlier high-level/direct-action and S=10 conditions. Its seeds, scores and “current evidence” are not the active 1× tactical controller. Use the [current PingPong workflow](../../../../../docs/tabletennis.md) and its seed11/seed12 records. The original report follows unchanged.

# sooool

GPT watches robot table tennis and makes online decisions. Development uses
ChatGPT subscription inference with measured API delays. The real-time API
validation has completed two valid native matches: a 5:1 win on seed 1009
and a 2:5 loss on seed 101. Reliability is not established.

This research adapter uses the native simulator, observation whitelist, high-level
action lowering and fresh-process replay. It is not an official Harbor trial.
The simulator, robot limits and referee are unchanged.

`protocol.json` records the resource boundaries and acceptance proposal.

- `preflight.py`: representative permitted camera observations and native match.
- `policy.py`: visual decision prompt and JSON action parser.
- `paid.py`: process-memory credentials and shared, locked budget reservations.
- `profile.py`: strictly serial real-image API latency measurement.
- `native_worker.py`: subscription-only native Codex connection, isolated from simulator files.
- `simulate.py`: online subscription decisions with sampled API delays and replay logs.
- `test_budget.py`: reservations, unknown charges and cache-accounting checks.

The profile must match the actual input and output shape. A profile consisting
mainly of wait/toss decisions does not establish full strike-planning latency.
Strategy, history, output and image changes require separate calibration or
explicit delay sensitivity before real API transfer.

Full logs and runtime dependencies live outside the source worktree; compact
evidence summaries are saved under `results/`. No credentials
belong in source, artifacts or log files.

Current evidence: `geometry_stable_early_chunk` won development seed 2 by 5:1
at L1 and slowdown S=10, with 146 logical model decisions. The run resumed a
verified continuous decision prefix after a subscription capacity failure. A
fresh native replay matched all 146 own-state observations and the final digest
exactly (`results/first-win/`). This is one development victory, not held-out
success, native-speed S=1 success, or a real API result.

The scalar public-flight helper matched 200 trajectories exactly and generated
identical candidate JSON for 11 recorded observations, about five times faster.
The optional public-referee watch woke at step 737 in a passive native check,
with zero game actions. Online subscription watch runs subsequently won seed 5
by 5:1 (126 decisions), seed 2 by 5:2 (158 decisions), and seed 6 by 5:2
(158 decisions). All 442 decision-camera PNGs and final native digests matched
in independent replays.
These development runs used the original delay profile, not the updated matched profile.

Task defaults were checked in `sports/tabletennis/sport.toml`: match level 1,
official slowdown 10, and success means winning a valid match. Thus L1/S=10
is the default target; S=1 and levels 2-4 are separate, harder conditions.
`profile_matched.py` prepares a balanced serial API recheck from exact saved
winning-game prompts and images; its default dry-run makes zero paid calls.

The balanced matched serial API profile has 24 valid decisions covering wait,
move, serve chunks and strikes: median 1.117 s, P95 1.870 s. Total paid usage
after both real-time matches is $16.629825 of the $30 limit; no requests are pending.
The seed-101 loss and native verification are retained in
`results/api-validation-seed101-v2/`. Native replay was exact; it was a game loss,
not a technical failure. Action diagnostics show joint-speed limitations and
late replanning, while requested absolute contact times matched within one tick.

`results/paired-hold-plan-v1.json` fixes the next subscription-only comparison:
baseline versus preserving an early committed stroke on development seeds 2 and 5,
using identical updated matched API delays, two episodes and one actual worker
per episode. It starts after the watch round to avoid increasing inference load.
Seed 101 has now informed development; reserve a fresh seed for subsequent
held-out acceptance rather than treating 101 as unseen.

A spectator replay of the actual 5:1 API match was exported at 10 video FPS,
one frame per .01 game-second tick, to preserve S=10 active wall-clock speed:
2216 frames, 221.6 seconds. Point-review pauses are omitted.

Both completed watch victories now have independent exact camera replay checks:
126 PNGs on seed 5 and 158 on seed 2, plus the final native digests.
`calibrate_api_return.py` restores actual API command history and branches only
recorded allowed candidate actions after a specified arrival delay. These fixed
physics diagnostics make no GPT performance claim. At observation step 1025,
the left return with .76 game seconds remaining won the point; central and right
returns missed with larger native planning errors. This is one diagnostic, not
a general direction rule. Later branches can include other original commands
that arrived before the branch and must be interpreted with that history.

The optional `_feedback_` condition exposes whitelisted native own-action error
feedback in `STATE.recent_applied`; it adds no hidden world fields. It has been
implemented and syntax/whitelist checked, but has not yet completed an online
GPT trial. It is not enabled in the queued baseline/hold comparison. Prompt
changes need calibration or delay sensitivity before another paid transfer.

The optional execution-feedback condition passed two subscription smoke inputs
from saved real API camera observations (legal act / wait choices; one input had
two nonempty execution-feedback records). These are schema/integration checks,
not online game wins or a latency estimate.

`results/native-action-delay-profile-v1.json` measures the existing native API
action completion times. Strike requests had medians 1.112 s / 1.097 s and maxima
3.721 s / 3.503 s in the two matches. These include planner/queue time; they are
not pure inference latencies. The current simulator does not independently charge
that elapsed time as controller blockage while physics catches up. Consequently,
its existing victories do not demonstrate robustness to this execution delay.
A separate future condition must block new observations, result consumption and
chunks during measured lowering time while letting physics and pending model
deadlines advance. Keep the existing paired-hold comparison unchanged. Cached
prefix recovery must restore logged blockage durations to remain causal and
reproducible; point-end boundaries must cancel obsolete work.

The `_executor_` mode now measures each local native lowering/apply duration,
blocks controller observations/results/chunks for its wall-clock equivalent,
and advances physics/pending deadlines meanwhile. It logs every block and
restores its original duration for a verified cached prefix. HTTP queue and
transport delays remain excluded. The native timing check passed twice,
including delayed responses and exact restored camera/prompt/native state.
These fixed-choice diagnostics are not GPT performance results. With the mode
disabled, the first 1000 ticks / 60 cached observations and all 17 commands of
the original fast-seed2 run matched, with no fresh model calls.

`defer_executor_round.py` is waiting for the complete paired-hold round. It selects
by paired wins then mean point share (baseline on ties), rejects incomplete
selection, and runs selected-policy versus optional feedback on development
seed 6 under execution blockage and 1.25x sampled matched API delays. That
multiplier is sensitivity, not profiling. Both jobs use one actual subscription
worker. The upcoming round now uses a two-second admission gap after throughput
measurement; the current hold round retains six seconds. No paid requests are scheduled.

The complete watch-versus-fast development comparison is retained in
`results/watch-vs-fast-development.json`: both won 3/3, but watch reduced calls
only 446 to 442 (0.9 percent) and mean point share fell .810 to .754. Watch is
not adopted as the current main direction. Research wall times are not compared:
the original fast seed2 used prefix recovery and subscription load differed.
The matched-profile baseline/hold round has now actually started; its executor
and feedback successor remains queued until complete paired selection is possible.

Acceptance freezing is implemented but acceptance is not yet started.
`prepare_acceptance.py` requires a completed, selected `_executor_` development
winner, all decision PNGs and final digest independently replayed, unchanged
strategy code, and the exact delay profile. It copies the profile and freezes
source Python, native core/tabletennis/renderers files and the actual subscription
model configuration (hashes only; no auth). It prepares all ten reserved seeds.
`run_round.py` optionally verifies that manifest before each launch and after
each result, including the episode's captured source/profile hashes. Changed
runs are incomplete and excluded, and later launches stop rather than mixing
policies. The accounting integration check passed locally and on the target host
with explicit fake workers, without model or API calls. Actual held-out games,
their native image replays, independent confirmation and final real API transfer
remain outstanding.

`calibrate_api_serve_timing.py` branched the first actual API serve in seeds
1009 and 101 at toss gaps 10/12/14 ticks, with and without a contact-time offset.
The saved 12 executions contain 10 distinct seed/gap/contact conditions (the
zero offset at gap 10 was duplicated, not an independent replication). The
original actual toss gap was 12 ticks in both sources. A +.02 s contact offset
at gap 12 recovered the service advantage on seed101 but lost it on seed1009.
No universal serve offset is adopted. These branches use fixed controls and
passive followup; a loss after opponent return is not proof the serve was illegal.
The gap-10 branches do not demonstrate the real controller can toss that soon
while its native windup planner blocks.

The first updated-profile development pair completed: baseline and hold both won
seed2 5:1, with 140 versus 154 decisions, and all 294 decision PNGs/final digests
passed independent replay. Seed5 remains in progress; no policy is selected yet.
`results/paired-hold-round-v1/throughput-seed2.json` separates actual subscription
turns from artificial shared admission waiting. Median turns were 2.555 / 2.538 s,
while median admission waits were 9.288 s in both arms. Admission waits consumed
1204 of 1618 s and 1400 of 1904 s, with zero capacity retries. Thus the existing
six-second global gap, not inference alone, dominated development time.
The wait-only executor successor was replaced before any of its games started:
it now uses a two-second gap with the same two-worker maximum, existing bounded
capacity backoff and causal prefix recovery. Current hold games were not changed.
Its actual speed/capacity outcome remains unmeasured. Acceptance preparation
now inherits the selected source round's admission gap rather than silently
restoring six seconds. Paid usage remains $16.629825.

The remaining seed5 episodes were subsequently resumed at gap2 using verified
continuous prefixes: 85 baseline and 59 hold requests, with every original step,
PNG hash, prompt and sampled/preprocessing delay matched before fresh decisions.
Their original processes inherited ignored SIGINT from background launch; after
confirming that, only the owned simulator parents were terminated and their
native workers finished/cleaned up through closed stdin. No replacement was
started until all old workers had exited. Interrupted fragments are not losses
or new independent games. `results/admission-resume-v1/` preserves this change.
Recovery now includes only logged issued decisions, excluding any unlogged
last worker result. Native execution-block restoration was rechecked afterward
without model calls. The resumed round reports full logical episode call counts;
throughput comparisons must exclude `reused_from.json` cached decisions.
The executor selector now merges the original completed seed2 pair with the
resumed seed5 pair, counts each logical job once, and rejects conflicting
completed native digests. Fresh requests at gap2 have started without retries;
full throughput and completed policy scores remain to be measured.

The resumed updated-profile baseline seed5 completed 5:1, with 144 logical
decisions including 85 reused decisions and 59 fresh calls. Independent replay
matched all 144 original camera PNGs, own-state observations and final digest.
Together with seed2 5:1, the baseline has won both completed matched-profile
development seeds. The hold seed5 result remains pending.
`audit_acceptance.py` now checks all ten frozen seeds, complete jobs, exact
source/profile/model/delay/task condition and every decision camera plus final
state against each independent native replay. Its accounting checks reject
missing camera verification and missing jobs. Its `stage_passed` applies only
to the frozen subscription stage; `goal_complete` is always false because
independent confirmation and real API transfer need separate evidence.

The complete matched-profile development comparison is now final: baseline
won seeds2/5 both 5:1 (284 logical decisions total); the additional hold prompt
won seed2 5:1 and lost seed5 3:5 (332 decisions). All 616 decision PNGs, own
states and native final digests passed independent replay. Selection followed
complete paired wins then mean point share: baseline2/.833 versus hold1/.604.
The hold prompt is rejected for the current main direction.
`results/paired-executor-round-v1/plan.json` records the successor that actually
started: selected baseline versus public execution feedback on development seed6,
native local execution blockage enabled, both with1.25x matched API delays and
gap2/two real workers. Source files are now kept unchanged during this round
so any selected verified winner can be frozen directly for acceptance.

Execution-delay development: public-feedback seed6 completed 5:1 with129
decisions, all PNGs/own states/final digest independently matched. The baseline
comparison experienced a confirmed120-second subscription request timeout at
score1:2; that technical fragment is incomplete and excluded, never a loss. It
is being causally resumed with the same policy, sampled API delays and restored
original execution-block durations.
The feedback acceptance plan has been prepared and its freeze verified:32
source Python files,183 native environment files and4 external model/runner
configuration files. It reserves all ten unseen seeds and changes no Python
source during the stage. A runtime-only launcher waits for a complete baseline
recovery and native camera replay before selecting the policy and starting the
frozen round, then replays each complete acceptance game and audits the stage.
It makes no paid calls. The1.25x sensitivity scales sampled completions while
policy timing hints retain the original measured API profile.

The execution-delay comparison is now complete and independently replayed:
baseline recovered its real subscription timeout prefix and won7:5 with249
logical decisions; feedback won5:1 with129. All378 decision PNGs, own-state
observations and both final digests matched. The timeout fragment is not a
second game or loss. Feedback is selected by the predeclared win/point-share
criterion; this one development seed alone does not establish generality.
Frozen acceptance actually started in `feedback-acceptance-round-v1`, first
seeds151/103, with ten reserved seeds total. No source Python, native environment
or model configuration changes are made during the round. Native camera replay
and the full audit are scheduled after the complete games. Paid usage remains
$16.629825, and final actual API transfer still awaits acceptance evidence.
