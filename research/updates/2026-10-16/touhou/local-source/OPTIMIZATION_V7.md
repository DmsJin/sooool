# Joint safety, tracking and resource optimization

The actor remains GPT choosing every executed direction, speed, duration, shot
and bomb from screenshots. The engine, Gym reward, scheduling and action
contract are unchanged. Private reference grids never select live actions.

Two experimental candidates compare local safe parking columns before Bomb:
`tracking_dodge_balanced_v7` is a shorter policy rewrite;
`tracking_dodge_local_gap_v7` appends a local check to the historical v2 policy.
Both use the existing accurate first-legal-cohort wording. Full task/schema and
visual grounding remain present; the default controller is not replaced.

The frozen screen used the original26 public fixtures, three candidates,
two fresh repeats, low effort/aggressive wrapper, twelve native workers.
156/156 answers were legal;264 original-engine counterfactuals were scored,
with four clone/public-browser final states validated. Paired delay endpoints
are correlated and this is development data, not held-out or realtime proof.

| Candidate | Instant hits/16 | Delayed feasible hits/52 | Bombs | Mean ordinary shot damage |
|---|---:|---:|---:|---:|
| Fresh v2 baseline |4|8|18|47.40|
| Balanced v7 |2|8|2|37.21|
| Local-gap v7 |2|13|8|45.29|

Neither candidate passed the unchanged four-condition development gate.
Balanced v7 reduced Bombs but did not preserve ordinary damage, and still
regressed on specific cases. E02/E04/E08 remained zero ordinary contact.
Do not describe correct direction, small motion, fewer Bombs or an aggregate
safety tie as having solved continuous tracking.

An independent audit distinguishes path collision from parking collision and
confirms some low-HP Bombs are genuine finishers. Early boss kills truncate the
ordinary-shot window. Therefore new closed-loop episodes separately compare
win, finish time, deaths, resources and firing misses; they do not rewrite the
frozen local score or constitute promotion. Historical API latency simulations
must be labeled separately from new paid API calibration and realtime trials.

Frozen policy SHA256:
`d1e25a8f1ee138ae83689909326255d108bc162cf043400c07c9d92eba658d18`.
Full outputs, private audit, protocol and unchanged-score summary are stored in
the task artifact `kaguya-optimization-v7`. The existing human annotations are
preserved. Paid API spend for this screen is zero.
