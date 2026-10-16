# Audit-only forecast output experiment

GPT optionally reports its own estimated boss velocity, application position,
movement endpoint and shot-arrival target before the chosen plan. The executor
continues to consume only plan. It never computes movement from forecast fields,
repairs inconsistent endpoints, selects safe alternatives or triggers Bombs.
Historical candidates retain the original schema and default behavior.

The frozen development screen used26 original public fixtures, three candidates,
two repeats and low/aggressive subscription turns.156/156 outputs passed actual
schema, finite/null/type and provenance checks;264 original-engine rollouts were
scored and four clone/public-browser finals matched.

| Candidate | Instant hits/16 | Delayed feasible hits/52 | Bombs | Mean ordinary shot damage |
|---|---:|---:|---:|---:|
| Fresh v2 baseline |4|8|20|44.13|
| v2 plus forecast fields |0|7|16|48.94|
| v8 math plus forecast fields |2|6|20|40.77|

Forecast-only v9 passed the unchanged four aggregate screening gates. This is
not promotion: E02/E04 remain zero ordinary contact and E08 regressed from0to2
hits. Fresh four-repeat confirmation failed (details below);
the default remains v2. Same-answer delay endpoints are correlated.

The104 forecast answers report endpoint arithmetic within0.06–0.10pixels on
average of displacement implied by their own estimates and chosen controls.
That measures internal consistency, not accurate perception, safety or actual
shot contact. Partial safe moves can legitimately stop short of an aim estimate.

API calibration tooling now infers the candidate's actual schema and rejects
fixture/schema/output-cap/detail mismatches before asking for credentials or
sending requests. Forecast candidates opt in to preserving native property order
on the API wire; legacy candidates keep their previous serialization. Canonical
structural schema hashes remain, with an additional ordered schema hash on the
new API path. This follows the official Structured Outputs key-order behavior:
https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses

API order/calibration fixes were made after the subscription screen froze and
have offline tests; no real API calls have validated the new path yet. Frozen
screen and confirmation sources are retained independently in the task artifact
kaguya-optimization-v9. No private GT/action grid is transmitted to actors.
Paid API spend for these experiments is zero; last read global settlement total
was21.6291402USD with no unknown/inflight requests. Full real calibration and
realtime validation remain required within the existing budget caps.


## Fresh confirmation rejected v9

The208-answer confirmation passed actual schema and provenance checks. Private
scoring produced352 original-engine rollouts; four clones matched public replay.

| Candidate | Instant hits/32 | Delayed feasible hits/104 | Bombs | Mean ordinary shot damage |
|---|---:|---:|---:|---:|
| Fresh v2 baseline |5|2|44|50.38|
| Forecast-only v9 |1|12|44|46.78|

V9 fails delayed safety and damage. Both candidates still produce zero ordinary
contact in the difficult E02/E04/E08 cases. The initial small-screen improvement
did not reproduce; forecast fields remain an experimental diagnostic format.
The repeated development fixtures and paired delay endpoints are correlated.

Fresh closed-loop reported outcomes (pending full four-episode replay audit):
seed9 baseline won53.383s/2hits, v9 survived60s with35HP/2hits; seed10 baseline
lost53.967s with795HP/3hits, v9 lost50.3s with265HP/3hits. Baseline wins1/2,
v9 wins0/2; these small samples do not establish a causal effect.

Both seed9 actual-actions replays independently match complete engine finals.
V9's longest ordinary-shot drought is8.53s vs baseline5.98s. Its forecast targets
alternate between overprediction at turns, trailing the boss, and anticipating
a return too early. Both runs' four collisions occurred after movement stopped.
Deaths during pending responses also made old player-at-apply predictions stale;
this occurs in both candidates and is not a displacement arithmetic error.
See the private task artifact episode9-failure-audit.json/md; none of this private
future evidence or reference actions is sent to actors.

V10 tests fixed non-homing shot/collision mechanics, then observed turn trend,
without changing the game, executor or default policy. Paid spend remains
unchanged; no API validation of a new candidate has yet been justified.
