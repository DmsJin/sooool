Read root AGENTS.md before starting services. This game uses hybrid control: SOL supplies conditional side/shot goals, recovery, horizon and memory.

The selected tactical-goal-v2 policy uses continuous camera interception and joint contact/launch search. SOL supplies one goal per conditional branch. Preserve the requested goal through contact corrections. Keep exact plans, legal projections and rule fallbacks separate. The tactical-v1 policy files remain historical evidence.

Subscription simulations use the default service tier with Fast explicitly disabled. Historical API Ultrafast measurements supply virtual delays only.

Use EGL GPU rendering and the pinned read-only RoboOlympics environment. Keep simulator truth in offline replay audits.

Retain failed runs. Do not automatically change or promote the policy.

Realtime evaluation uses actual Ultrafast API responses and the recipe's slowdown
(currently S3; retain earlier S2 evidence). Keep physics
independent of camera control and planning. Drop late plans instead of running
the native synchronous replan path. English public summaries accompany the same
API intent. Video is a verified native replay with recorded acceptance times.
