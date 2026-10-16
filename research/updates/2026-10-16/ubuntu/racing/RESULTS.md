> Correction: historical subscription visual trials using `Native` with `localImage detail=low` omitted image contents. They do not establish GPT visual driving. The adapter is corrected and inline image hashes verified. Direct API calls bypass that Codex image preprocessor. See [strict native-action report](native_action/REPORT.md). Prior hybrid wins remain outside the current strict native-actuator goal.

# Robot Racing research results

## Clarification: coded visual policy is a substantial component

This is not pure GPT image-to-speed/steering control. A coded vision controller
reads fresh intermediate frames at5Hz, extracts the yellow stripe, calculates
pure-pursuit steering toward the GPT-selected stripe offset, and caps speed using
curvature. GPT selects speed, lane offset and lookahead roughly every0.6s, subject
to actual response delay. The code can adjust steering on frames GPT never sees.
This exceeds action holding or open-loop action chunking.

A no-GPT fixed-goal camera-controller preflight also won (free-http-lane-1x-v15).
Therefore the current evidence does not establish that GPT is necessary for the
win or improves over a coded baseline. Direct GPT steering at1x remains unproven;
the successful direct-steering API cases were at5x slowdown. Any previous broad
claim of a pure GPT raw1x solve should be read as withdrawn. The actual verified
win is specifically the hybrid controller described above.

Canonical final results for real API seed304 show two normal finish wins, all16
checkpoints in each heat, zero own warnings and one obstacle crash. No reward or
referee modification, hidden pose or hidden progress is used by the live policy.
Replay validity proves trajectory consistency, not GPT indispensability.


The workflow has produced a complete **Level1 match win at1x real speed using
actual streaming OpenAI API decisions**. The controller is hierarchical: GPT sees
camera frames throughout the race and selects finite speed/lane-offset/lookahead
goals; a5Hz visual executor follows that selected offset. It does not choose a lane
or obstacle maneuver itself. Goals expire3 game seconds after their observation
and the car brakes without a fresh model goal. This is distinct from direct GPT
steering and from the camera-reference executor preflight.

## Verified real API result

Unseen seed204, Level1/1x, original visual-lane policy:

- Match2:0,32 checkpoints, zero own warnings and zero obstacle crashes.
- Actual model gpt-6.1-sol / low / ultrafast, minimal system;93 calls.
- Physics59.68 game seconds in59.686879 wall seconds; whole validation72.693344s
  including heat review, draining model requests and final replay verification.
- Canonical valid_trial=true and deterministic=true; lagP99 8.147ms/max13.963ms.
-299/300 submitted commands took effect; one crossed a heat/end boundary.
- Canonical player mode=model; no metering/proxy errors, no HTTP429, peak17HTTP/s.
-92 eligible live calls all published before response.completed; paired median
  stream-end saving92.053ms. The pre-start registration call waits for completion.
- No artificial model delay, no pause of physics during thinking.

Artifacts: `evidence/results/api-live-lane-1x-s204-v1/` includes canonical final,
fresh-process replay result, source snapshots, request/action logs and identity/
budget audit. Full original inputs, images and result files remain in the isolated
server experiment under the matching result directory.

The final lane-commit prompt has separately won all three development seeds and
has also won actual API raw1x verification on unseen seed304. It makes
lane offset explicitly stripe-relative, preserves a safe lane when overtaking,
and avoids switching sides merely for a bend. The controller implementation is
otherwise unchanged. Its independent frozen holdouts301/302/303 also won3/3, each complete with a
matching independent replay. The candidate was frozen before those tests. Both variants now have their own real API verification.

## Full subscription comparisons

All simulations use actual subscription model decisions from real images, with
measured serial API delays imposed causally. Native model computation may make
the experiment take longer in wall time, but answers cannot affect the simulation
before their scheduled arrival. Incomplete episodes are not scored as losses.

| Policy | Slowdown | Development seeds | Full group wins |
|---|---:|---|---:|
| Bounded finite waypoint |1|101/111/121|0/3|
| Waypoint with curvature speed cap |1|101/111/121|0/3|
| Original visual-lane goals |1|101/111/121|2/3|
| Lane-commit visual goals |1|101/111/121|3/3|
| Direct metric steering, minimal outer |5|101/111/121|3/3|

All completed group results require matching independent replay hashes. The
selected5x steering policy also won frozen holdout seeds1/2/3 and two actual API
matches, seeds101 and4. These are5x results and are not1x evidence. The original visual-lane policy also won its independent raw1x frozen holdouts
201/202/203,3/3 with matching replays (seed203 needed three heats).

## Profiling, outer prompt and streaming

Initial32 paid API profiling requests were strictly serial: fastest0.983757s,
median1.350020s,P95 2.258153s. This distribution was sampled for subscription
simulation. A later16-call serial check used actual frozen winning-policy inputs
and the minimal system: median1.431529s. It ran under background subscription load
and does not replace the initial fastest-API profiling.

The selected minimal Codex outer follows the user's supplied system text, isolated
CODEX_HOME and requested feature flags. It preserves the game task, observations
and output format. The24-pair interleaved A/B did not show a speedup: mean8.384→
13.328s, median8.206→12.317s. The user explicitly selected the minimal outer anyway.
Actual wire inspection found that Codex still injects multi-agent instruction
blocks and additional tool definitions despite the flags. This is partial outer
minimization, not a proven tool-free request. High account concurrency remains a
possible explanation for timing differences, not an established causal finding.
See `PROMPT_AB_REPORT.md` for the controlled measurements.

The API client originally waited for SSE EOF. It now validates the complete JSON
array after each delta and publishes a legal action as soon as returned model/tier
are known. A separate completion future drains the stream and settles usage. A
later error or changed final action invalidates the match. Serial profiling stays
serial. Eight same-request paired measurements gave median availability1.352201s
instead of1.443043s at EOF: paired median saving90.838ms. See
`API_STREAMING_REPORT.md`;13 contract tests currently pass.

## Cost and limits

The process-locked shared ledger enforces USD30 including all outstanding requests.
It conservatively prices all input at the cache-write rate and retains full reserved
cost for uncertain failures. Credentials enter getpass and child-process memory
only; no credential is written to repository files or result artifacts.

Paid upper-bound cost after the first1x API win was$17.745405 with zero outstanding
reservations. After final-policy validation on seed304, the conservative ledger is$19.581030
with zero reservations. No paid requests remain active. Subscription jobs never fall back to paid API.

Verification uses the repository's actual HTTP service, unmodified canonical
metering proxy pointed at api.openai.com, continuous wall-clock physics and
fresh-process deterministic replay. Harbor container isolation is not implemented;
these results are not claimed as an isolated official Harbor submission. Level2–4,
duel and multi-car race are separate configurations and are not claimed solved.


Final candidate real API seed304: WON2:0;82 actual returned model/tier identities
checked;161 actual input-image hashes checked;238 nonbraking commands linked to
existing unexpired GPT goals.260/260 actions applied; no invalid outputs; no429;
peak17HTTPrequests/s. Canonical model mode, valid_trial=true, deterministic=true,
no metering/proxy errors. Physics51.79game/51.795318wall seconds, whole trial61.586836s.
LagP99 4.969ms/max8.775ms.81/81 eligible calls published before completed, paired
median EOF saving85.933ms. Archived source snapshots exactly match the tested immutable remote source.
The independent entrypoints relocate environment/budget paths; policy and API
client ASTs, lane bytes, and the live loop otherwise match the tested snapshots. Artifacts are in the matching evidence folder.

Final frozen lane-commit holdouts: seed302:WIN,49.19game seconds,83calls, seed303:WIN,49.15game seconds,83calls, seed301:WIN,53.72game seconds,91calls. All3 independent replay hashes match.
