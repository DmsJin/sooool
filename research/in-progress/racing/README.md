# Robot Racing continuous research

**Stopped at the user's request after the outer-prompt A/B test (2026-10-15).**
See [PROMPT_AB_REPORT.md](PROMPT_AB_REPORT.md). The original completion criteria
below describe the earlier research target; no final real-API race was performed.

The user subsequently selected the minimal subscription outer prompt as the
default. `Native()` now uses the isolated minimal configuration; the earlier
outer remains available explicitly as `Native(..., outer='current')` for A/B.
This choice does not restart experiments. High account concurrency is a possible,
unverified explanation for the observed timing; the original measurements stand.

User authorization: gpt-6.1-sol, low reasoning, ultrafast API; total paid ceiling
USD 30. Subscription experiments may run concurrently. Initial API profiling is
strictly serial. Final confirmation must use real API decisions while physics
continues on a wall clock. Do not call a slowed or simulated win a real-speed win.

Source environment: CHIGUI0/roboolympics at da1f787f. Development checkout is a
separate worktree, /tmp/roboolympics-autoresearch. Deployed isolated experiment:
/home/ubuntu/wzh/racing-autoresearch-20261015. No credentials in this repository.

## Acceptance

Single-player `racing-match`, first to two heat wins. Begin at Level 1, then report
each higher level separately. Three development seeds 101/111/121 at Level 1,
followed by a frozen full-group confirmation and untouched holdout seeds. Incomplete
episodes are never scored as losses. Only full episodes with matching independent
replay hashes can enter a complete group result. A Level 1 win does not solve all
four levels. Primary goal is 1x real speed; slowdown is always reported.

Observations: published car cameras, own telemetry, referee messages and public
spec only. No true pose, live track progress, opponent state, hidden seed or future
delay enters a policy. The `metric` variant adds coordinates extracted solely from
the same camera pixels and published camera calibration; it is a distinct input
condition. It does not call the reference controller for actions.

## Verified so far

- Free reference-controller preflight: complete two-heat win at seed 101/Level 1;
  fresh-process replay hash matches. This is environment validation, not GPT success.
- 32 serial direct API decisions, each one actual 240x160 camera image, valid output:
  fastest 0.983757s, median 1.350020s, P95 2.258153s, mean 1.472149s.
- Conservative paid-cost upper bound after profiling: USD 0.38406; no pending paid
  reservations. This upper bound charges all input at the cache-write rate.
- Subscription native probe produced an actual valid command from a racing image.
- Three budget/action contract tests passed, including independent concurrent cost
  reservations and retention of uncertain-request costs.

## Runs and entry points

- `results/profile-serial-v2/profile.json`: measured serial API distribution.
- `results/round1`: frozen direct-image basic/anticipation policies, 1x and 5x.
  Up to eight episodes and three real subscription workers per episode.
- `results/round2`: camera-metric candidate, Level 1 seeds 101/111/121, 1x.
  At most two episodes concurrently to preserve memory headroom.
- Each episode has config hashes, issued requests, images, returned commands,
  arrival times, applied-command episode log, and independent replay output.
- `research-results/budget.json`: one process-locked paid ledger for all stages.

Subscription simulation samples measured real API delay and divides by slowdown
to obtain game delay. Already computed answers remain unavailable until their
scheduled arrival. At an arrival the virtual clock may wait for actual subscription
computation, without letting actual computation time alter virtual dynamics.

The built-in reference policy is used ONLY by the free environment preflight.
The real-time validator `live.py` uses the canonical HTTP service, its actual
wall-clock physics and its unmodified metering proxy pointed at api.openai.com.
It does not provide Harbor seat isolation; report this limitation separately from
replay and timing validity. API credentials enter only via getpass and remain in
process memory. Never copy credentials into reports, logs or source bundles.

Transport probes are separate artifacts and must not be confused with policy
evaluations. Built-in native WebSocket requests received 403 retries. Custom SSE
native transport worked but did not by itself establish a throughput improvement;
a minimal controller instruction plus low-detail image probe took 14.5s, compared
with roughly 25-30s initial native decisions. All subscription wall times are distinct
from the measured API delays used for simulation.
