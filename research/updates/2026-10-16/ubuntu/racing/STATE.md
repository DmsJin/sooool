# Current checkpoint — 2026-10-16

STRICT native GPT control remains UNSOLVED. Raw legal camera images plus own/referee
telemetry only; no CV or code driving policy. External roboolympics is read-only.

Paid authoritative ledger: remote research-results/budget.json, charged upper
21.391185USD of30USD, no reservations/no paid requests active. Never overwrite it
with the local ledger. Latest six serial stateful single-action API calls all valid:
median1.597295075s, mean1.590477001s, range1.357798335–1.773820115s.

Completed valid-image trials:
- native-full-v1:4 stateless fullmatches, all lost0:2, replay/executor audit pass.
- native-curriculum-v1:20 slowed5x12s prefixes,19prefixes+1DQ loss; no win.
- native-session-v1:4 continuous-conversation12s prefixes; no fullmatch claims.
- native-forecast-v1:20 forecast/three-action12s prefixes; no fullmatch claims.
- native-forecast-full-v1:20 fullmatches, ALL LOST0:2; replay/executor audit pass.
- native-single-v1:20 one-command/max3s-validity12s prefixes; all replay and
  exact actuator audits pass, no complete match wins established.

CURRENTLY RUNNING: native-single-full-v1,20 fullmatches at1x, five prompts x four
seeds101/111/121/131; native-single-curriculum-v1,4 fullmatches at2x/5x for diagnosis.
One causal conversation/one pending request per episode, raw three-image history,
arrival anchoring, GPT chooses exact speed/steering/duration up to3s; new GPT plan
replaces prior plan. Executor only delivers/expires commands. Game supports held
commands; three-second limit is our executor validity, not an environment edit.
Native timing now logs legal JSON availability separately from whole-turn return.
Subscription actual tier remains UNVERIFIED; direct API tier is verifiedultrafast.

live.py now accepts stateful session/forecast and max-duration3; captures images
while a call is pending and gates the next session call on full stream drain.
Opt-in conservative cache-aware budget caps preserve old cumulative charges.
COMPILED ONLY: new live session mode has NOT been exercised against a real HTTP
match or paid API. Do not claim strict real-time solve based on this scaffolding.
15 shared stream/contract/stateful/budget tests passed. Final path still needs a
suitable raw-image candidate, held-out simulator validation and true1x API match.

--- Historical checkpoints; invalid-image findings supersede older native claims ---

# Critical image-input correction

The initial strict native subscription screening rounds v1/v2/v3 are INVALID for visual-policy evaluation.
A localhost wire intercept proved Codex localImage detail=low emits textual
"image content omitted because detail low is not supported" instead of input_image.
This also affects historical subscription trials using that Native adapter: they
cannot establish that GPT saw camera frames. Hybrid numeric CV inputs were still
present in older trials; this is another reason not to claim native visual solving.
Direct paid API calls attach image data directly and do not use the Codex localImage
preprocessor; the 24-call native API profiling results are retained.

Native adapter corrected to detail=auto. Verify inline wire hashes before running
new subscription episodes. No CV or steering controller is added.
Cumulative paid upper20.14824USD /30USD, zero reserved; authoritative remote ledger unchanged.

--- Earlier research state, superseded where contradicted above ---

# Active strict native-action research

The prior hybrid lane-goal wins below are historical and DO NOT solve the current goal.
The camera pure-pursuit executor also won with constant goals; GPT necessity was not established.

Current goal: raw legal front/chase camera frames and own telemetry -> GPT directly
emits speed/steering/duration. native_action/executor.py is blind timed delivery only.
No CV, ground path extraction, pure pursuit, route following, reactive recovery or speed caps.
All development is independent; upstream roboolympics remains a read-only environment.

Strict serial paid native profiling completed 24/24 valid responses. Median action availability:
2images/1action 1.293s; 3images/1action 1.328s; 2images/3actions 1.599s; 3images/3actions 1.704s.
Six samples per condition: maximum sample is not a statistically robust population P95.
Remote authoritative cumulative ledger: research-results/budget.json, charged upper20.14824USD,
zero reserves, total cap30USD. Never overwrite this ledger with a stale local copy.

Native screen v1: six 18-second seed101 prefixes, all replay hashes match, no invalid outputs.
All variants hit walls or spend substantial time stalled/reversing. No full-match win claimed.
Next iteration tests official chase camera and explicit steering/yaw calibration in model prompt.
Chase simulations provisionally reuse same image-count/action-count latency distribution;
a promising new prompt/camera must be reprofiled before final real API validation.

--- Historical hybrid handoff (superseded scope) ---

# Final independent research handoff

Project:/home/ubuntu/wzh/robot-racing-research (server),/tmp/robot-racing-research (local).
Environment is only a read-only dependency:/home/ubuntu/wzh/racing-autoresearch-20261015
or local/tmp/robot-racing-environment at original da1f787f775ea6524d698c0b063157ded4c0fef9.
Never push to roboolympics or create a PR there. The mistaken PR163 was closed,
its branch deleted, and archived; privileged repository users can still see it.
No external support message was sent.

Goal achieved for Level1 single-player match at1x: final lane-commit policy won
all3development seeds101/111/121 and3frozen new holdouts301/302/303, replay matching.
Real API seed304:2:0win,82calls,161verifiedimages,260/260actions applied,
238nonbraking actions linked to unexpired GPT goals. valid_trial/deterministictrue.
Physics51.79game seconds/51.795318wall; whole verification61.586836wall seconds.
No artificial delays. Modelgpt-6.1-sol,reasoninglow,ultrafast,selectedminimal system.
GPT sees images and chooses speed/lane/lookahead;5Hz pixel feedback tracks that
finite goal, cannot select a route itself, and brakes after3game seconds without
fresh decisions. No claim of directGPTsteering,Level2-4,duel,race orHarborisolation.

Initial APIprofiling32strictlyserialcalls. Subscription simulations causally sampled
that distribution. Stream optimization publishes complete legalJSON before SSEend,
while workers continue validating and settlingusage;81/81eligible final calls were
published beforecompleted; paired median saving85.933ms. No paid calls active.
Conservative ledger$19.58103/$30,zero reserves. Keep this ledger for any future run.

All own episode processes are terminal. Own13contracttests pass locally and remotely
after relocation. Policy/APIASTs and lane bytes match tested immutable snapshots;
only environment/budget/executable path configuration changed. Old remote records
retained as archives; five final result directories copied and hashchecked into
independent project/results. Local original experiment files also preserved.

Main remaining limitation is scope, not incomplete Level1 verification: higher
levels and other formats remain separate future research. Detailed evidence is
in RESULTS.md,evidence/results and remote results. No further spending authorized
beyond the remaining global session budget without preserving cumulative ledger.
