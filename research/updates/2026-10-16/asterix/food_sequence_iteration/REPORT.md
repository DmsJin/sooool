# Sequential-food prompt iteration (in progress)

User feedback: V28 should pursue additional reachable food, including the upper food in the C06b screenshot at frame 507. All action choices remain native Sol outputs; no new code selects targets, directions, or prescribed action sequences. HopControllerV3 remains unchanged.

The original V28 continuation chose UP from observations 492, 496, 500, 504, 508 and 512. First executed UP was frame 518 from observation 496. A DOWNLEFT issued from observation 472 had already executed at489, before later upper-food observations could take effect. This supports investigating pickup handoff and latency, rather than claiming the model never chose UP. The earlier three-game-second clip is insufficient to establish longer food collection quality.

V30 changed both pickup handoff and target ranking. Four fresh restored-state continuations ran for300 raw frames (five game seconds) from the same C06b state, with two matched delay draws per strategy, minimal wrapper, native gpt-6.1-sol decisions and eight workers, subscription guard80%. Model wall time pauses the simulated environment. No paid API calls occurred.

| Policy | Repeat | Additional reward | Final lives | Reward frames |
|---|---:|---:|---:|---|
| V28 | 0 |150|2|484,620,687|
| V28 | 1 |150|2|472,544,592|
| V30 | 0 |0|1|none|
| V30 | 1 |150|2|453,556,635|

V30 is rejected: it did not improve reward and added a life loss. Four rollouts,296 request image sets, controller execution, rewards and lives were independently replay-verified without model calls. Artifacts are under `v30-paired/`, containing only curated public logs and video, no worker homes or credentials.

V31 keeps V28's scoring paragraph and changes only D2, broadening post-pickup handoff symmetrically and requiring an actual predicted intersection before treating food as already collected. It is not validated or promoted. A live sequential server job runs36 focused observations,104 old/new regression tasks and two five-game-second V31 continuations. The focused states are extracted from the actual historical V28 trajectory at472,480,488,500,504,508, preserving three chronological images and causal history. No ground truth or route is injected into inference.

Future decisions must consider actual reward and life loss, target timing and preserved regression safety together. Unit preference agreement alone cannot establish more food collection. Native timing is not API latency. The sampled latency profile contains valid-response delays and does not simulate provider failures. Two repeated continuations from a single restored seed are preliminary, not general performance proof.

## V31 frozen results

All36 focused tasks completed without runner errors. Atframe488, UP increased from1/3(V28) to2/3(V31), but atframe500 V31 selected LEFT once instead of UP; this is mixed evidence, and the pre-hop capture may be discarded by V3. No trajectory improvement is inferred from this distribution.

All104 regression tasks completed: paired V28 scored49/52 (old34/36,new15/16), V31 scored47/52 (old33/36,new14/16). Both retained C10b DOWN2/2. V28 had no observed head-on or new landing violations; V31 chose RIGHT2 in C05b repeat1 (repeat0 correctly choseUPLEFT6), a head-on violation. V31 is rejected for adoption. Its already-started two native continuations remain diagnostic and will drain; a high reward there cannot override the regression failure.

V32 starts from V28 and changes only the adjacent-row arrival-crossing paragraph. It distinguishes capture-time alignment from occupancy during the actual row hop, emphasizing passage behind an enemy that moves away, while preserving current-row emergency rules and the original D2/scoring text. This hypothesis is motivated by C12a's missed upper-food opportunity. No actions or route are supplied by code.

The live sequential V32 driver waits for the current V31 diagnostic to exit, then runs48 focus tasks. It continues only if C12 UP-family agreement improves against paired V28 to at least5/6; this is a pilot filter, not a promotion criterion. It then runs104 regression tasks, requiring no observed head-on/landing or C05b failure, C10b2/2 and overall agreement at least paired V28. Only passing candidates proceed to native-model C12a continuations (two matched delay draws per policy,300 raw frames each). General scoring improvement remains unproven and will require additional trajectory evidence beyond these filters. The goal remains active.

## Later premature handoff found in extended V28 video

The fresh V28 repeat0 had already reached the user's upper-food row by frame546 and began LEFT pursuit571. It then left that row via UPRIGHT590 from observation568, before any second reward. The next reward620 occurs with P on a different, higher row (confirmed by the extended contact sheet), so it does not demonstrate collection of the particular food visible in the user screenshot. This is a stronger behavioral failure to investigate than only the initial delayed UP.

At capture568 the actual held action wasNOOP; the selectedUPRIGHT arrived590. One hypothesis is premature switching based on an imagined horizontal pickup before arrival. No internal reasoning is available, so this cause remains hypothetical. V33 replaces only V28's pickup-prediction sentence, requiring prediction from actual held movement and maintaining horizontal pursuit when same-row food moves away from a stationary P. It preserves emergency instructions, controller and output format.

Two new causal diagnostic observations560/568 (C18a/b) were extracted from the independently verified V28 repeat0 trajectory. They carry the original three images and applied history; no target coordinates or oracle action is injected. LEFT is a provisional preference following the existing current-row-first principle, not a newly certified human annotation. Twelve V28/V33 native tasks are queued before the V32 pilot, within the same sequential eight-worker driver and subscription80% guard. The waiting driver was replaced; ongoing native requests were not interrupted or restarted. No new model scoring gains are established yet.

## Completed V31 continuations and new pilots

Both V31 continuations completed300 new frames. Additional rewards were50 and100 (final lives2/2), versus150/150 for the two earlier matched V28 delay draws. Independent replay verified147 new request image sets and all controller/reward/life records. Together with its regression failure, V31 is rejected; no scoring improvement is claimed.

V33's12-task handoff pilot completed without errors: V28 chose LEFT3/3 atC18a and2/3 atC18b (oneUPRIGHT); V33 chose LEFT3/3 in both. This is one improved sample, not a statistically established reduction or actual pickup gain. A sequential driver is queued for a260-task randomized paired comparison (26 frozen cases×5 repeats×2 policies). It requires V33 agreement at least123/130 and at least paired V28, no observed forbidden head-on/landing or C05b failure, and C10b5/5 before running two fresh V28/V33 C06b continuations each. All tasks remain subscription-only with an80% guard.

V32's48-task arrival-crossing pilot completed without errors. OnC12a/b, V28 chose UP-family5/6 and V32 chose it6/6, passing the exploratory filter; V32 is now running104 regression tasks. Its actual scoring benefit remains unproven. These two small pilots do not establish stable food pursuit or completion of the broader objective. Complete multi-seed5x trajectories remain necessary before general policy promotion.

## Full V32 and V33 paired regression results

V32 completed104 tasks:49/52 versus pairedV28 51/52. V32 missed one each ofC02a(RIGHT), C06b(NOOP), C08a(DOWNLEFT); it had no observed forbidden-direction violations, C05b2/2 and C10b2/2. Its pilot improvement onC12 did not translate to overall preference improvement. The original gate correctly stopped its C12 trajectory stage. It is not adopted.

V33 completed260 tasks:121/130 versus pairedV28 122/130 and fixed historicalV28 123/130. Old guard agreement was87/90 versus86/90; new route agreement34/40 versus36/40. V33 had no observed forbidden directions, C05b5/5 and C10b5/5. Both variants missedC02a twice and C12a/b three/one times; V33 additionally missedC09a once,C13a once,C14a once. V28 missedC05b once(NOOP) and C10a once(DOWN). V33 does not pass the adoption gate. This one-sample paired difference is not proof of an expected degradation or of actual food reward.

The next phase changes the evaluation sequence explicitly: retain the failed gate and all labels, but run an exploratory native-policy food-reward diagnostic to test whether completing current food is a useful direction. This is not policy adoption or relabeling. V34 is a concise equivalent of V33's held-trajectory clarification, retaining the rest ofV28. It first runs42 focused tasks; inclusion in the actual diagnostic requires criticalC05b/C06b/C10b9/9, C18 LEFT6/6 and no malformed actions. V28 and V33 are already scheduled for the diagnostic; V34 is conditional. All variants use the same verified C06b restore, two matched delay draws,300 raw frames, and a randomized episode submission order recorded in`episode_schedule.json`. Code still only transports observations, model actions and existing V3 execution; it does not choose food targets or directions. Independent zero-model replay follows the run. Actual score/life improvement, completing the user's upper-food target, preserving original preferences, and broader5x trajectories remain unproven requirements.

## First verified actual food improvement: V33

The randomized actual diagnostic completed four fresh model-controlled300-frame continuations:

| Policy | Repeat0 extra reward | Repeat1 extra reward | Final lives |
|---|---:|---:|---|
| V28 |100|150|2,2|
| V33 |200|150|2,2|

Independent replay verified all296 request image sets, all controller actions and all rewards/lives. InV33 repeat0 the original upper food is visibly collected at613, followed by pickups641 and679 (first pickup484). It stays LEFT through590 instead of leaving early. The pickup contact sheet shows a new50 popup in the target's row, then two additional rows' pickups. The paired comparison video is`v33-actual-diagnostic/v28-v33-repeat0-5x.mp4` (leftV28,rightV33,12FPS).

Against the earlier V28 repeat0 used to mineC18, V33's executed actions are identical until590. Its three images atcapture568 and heldNOOP are byte-identical; V28 choseUPRIGHT5, V33 choseLEFT3, both scheduled590. This is a direct behavioral demonstration on a development case, not evidence of unseen-state generalization. The same-batch V28 repeat0 diverged earlier489, so its whole rollout improvement cannot be attributed solely to568. Earlier V28 paired repeats were150/150; the baseline itself varies. Two current pairs cannot establish a stable expected40% improvement.

V34 focus completed42 tasks: critical8/9 versusV28 9/9, C18 LEFT6/6 forboth, C12 UP6/6 versus4/6. Its C06b NOOP miss excluded it from actual trials. V34 is not adopted.

A new shared-pool comparator calls the unchanged`simulate_5x.run_episode` for six fresh20-game-second games: V28/V33 on seeds2,5,6, randomized policy/seed scheduling, one shared8-worker native pool, V3, low reasoning, minimal wrapper, and held-out delay seed offset91. Every game starts from reset, with no reused model replies or recorded action prefix. It retains the historical measured API latency profile and80% quota guard. Fourteen offline prerequisite/scheduling checks passed; three scheduling checks also passed under the server Python. These checks validate orchestration, not policy quality. The six actual games are now running, output`/home/ubuntu/wzh/expts-sol/results/asterix/food-sequence-v28-v33-full20-20261015`.

V33 remains provisional. Its frozen regression gate still failed121/130 versus122/130 paired and123/130 historical. Broader score/survival, independent non-regression and stability remain unproven. Current realtime policy pointers are unchanged. No paid API calls were made.
