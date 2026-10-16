> **Retained source-harness research record.** This report/protocol describes its original experiment stage. “Current”, “ongoing”, “selected” and acceptance statements below belong to that stage; use the [selected Touhou learning record](../../../../../../docs/touhou-research-record.md) for the released policy, actual API wins and current launcher status. The original report follows unchanged.

# Tracking candidates and fixed public cases

Two additive prompt candidates extend the unchanged `tracking_dodge_adaptive`:

- `tracking_dodge_intercept_hold`: select a useful firing column across the subsequent idle firing interval, rather than only matching the newest boss x.
- `tracking_dodge_turn_guard`: compare continued drift with a visually plausible return pass before choosing direction. Uncertain reversal is not permission to extrapolate old motion across the arena.

Both retain safety priority, continuous shooting, focused correction as default, and adequate correction when clearly displaced. They use only original screenshots, already-returned controls, historical latency summaries and their own past visual estimates. No phase lookup, boss equation, future target or automatic steering is introduced. The engine, executor, one-action/48-frame limit and old prompts are unchanged.

## Diagnosis of the original win

The user's 17–28 seconds refer to VIDEO VISUAL time, which includes frozen spell declarations. Engine logical time differs. The original applied controls are:

| Source request | Screenshot visual second | Action visual second | Action | Logical seconds stationary until next action after plan |
|---|---:|---:|---|---:|
| 16 | 13.42 | 16.98 | focused left 28 frames | 3.27 |
| 21 | 17.78 | 20.72 | focused right 40 frames + bomb | 1.37 |
| 24 | 21.50 | 24.03 | stay 12 frames | 2.28 |
| 29 | 25.08 | 27.48 | focused right 13 frames | 3.00 |

Request 16's newest screenshot shows player x≈218 and boss x≈170. Applying a left correction over three seconds later can chase an old endpoint. Request 24 holds a column after a reversal forecast; request 29 resumes a small right correction. This is not evidence that the move key was misinterpreted. Prediction and the long stationary shooting interval need evaluation. The 48-frame maximum permits at most 0.8 logical seconds of continuous focused motion; moving in tiny chunks alone cannot guarantee sustained tracking across a ~2.7-second response gap. We do not yet change chunking/executor because it would mix causes.

## Frozen case set

`tracking_cases_v1.json` chooses API sequences 8/12/16/20/24/28/32/36 and human observations 148/301/671/1393 before candidate comparison. Each four-way API cohort shares the same input, so its first sequence is sufficient. API sequences 16–28 cover the user's mismatch; surrounding samples supply both excursions. Human samples supply alternate trajectories and clear/ambiguous tracking. This is a DEVELOPMENT set, not held-out evidence.

`tracking_cases.py` reuses original bytes with SHA-256 checks, copies future references exclusively to `private/`, and restores only original issued prompt's past visual memory. It rejects unsupported keys/future frames/nonfinite coordinates. The model never receives source answers or future human controls. All candidates get identical per-case memories. `aim_x` is an audit estimate, never an actuator target.

Build (paths are caller supplied; output must not exist):

```bash
python3 -m research.tracking_cases \
  --api-root /path/to/kaguya-api-win \
  --human-dataset /path/to/touhou-human-devset-v1 \
  --profile /path/to/actual-early-control-profile.json \
  --output /path/to/tracking-devset-v1
python3 -m research.visual_devset compare \
  --dataset /path/to/tracking-devset-v1 --output /path/to/comparison-v1 \
  --suite /path/to/coding-agent-suite --limit 12 --repeats 2 --workers 12 \
  --envelope aggressive \
  --candidates tracking_dodge_adaptive tracking_dodge_intercept_hold tracking_dodge_turn_guard
```

The actual early-delivery control-age profile supplied by the parent audit is median 2.69135 seconds / P95 3.170205 seconds, `control_age_kind=observed`. These values are a historical distribution, not the sampled current request latency. Individual screenshot-to-application gaps can be longer.

Score sustained shot damage, missed-fire intervals and safety using PRIVATE counterfactual rollouts at both delays, including at least the subsequent idle interval. Do not reward raw movement, proximity alone, bombs' direct damage, or a single gold direction. Source episode engine truth is allowed only in scorer/replay. Human undelayed reference actions are descriptive, not fair latency-matched policy wins. Candidate ranking remains unmeasured until comparison and private rollouts finish; true API validation must remain original uninterrupted 1x with all terminal accounts checked.
