# SOL researches a visual Asterix policy

The working object is a prompt and an observation/action contract. SOL sees game screenshots, their public timestamps, and its own applied-action history. It selects every direction. It receives no sprite coordinates, future frames, future response delays, target detector, or scripted escape route.

Humans identified dangerous decisions and reviewed trajectories. SOL turned that feedback into hypotheses, prompt candidates, evaluation scripts, repeated comparisons, and replay checks. The useful loop was **observe a failure → change a hypothesis → freeze the prompt → evaluate → inspect actual pickups and deaths → retain or reject**.

## 1. Make survival decisions explicit

Early clips showed the player moving toward approaching enemies. Human annotations supplied acceptable action sets for 18 core screenshots. Prompt iterations distinguished the yellow player, pale fork-shaped lyres, rounded food, and white score popups; they made current-row retreat and emergency escape higher priority than scoring.

V16's frozen five-repeat confirmation reached 86/90 preference agreement, with zero observed forbidden head-on directions and 5/5 emergency escapes. This was a screenshot-development result. It did not guarantee the next game would survive.

## 2. Optimize actual food pursuit

New video reviews exposed waiting beside reachable food, abandoning a current-row pickup, and missing the next pickup after collecting one. Four events produced eight related route observations; the benchmark grew to 26 cases.

| Candidate | Evidence | Decision |
|---|---|---|
| V20 | New-route pilot 23/24; frozen confirmation had head-on errors and dangerous lower landings | Reject despite the attractive pilot |
| V22 | Original-case screening 49/54; new-route screening 19/24 | New-route agreement insufficient |
| V23 | Frozen confirmation 116/130; one emergency head-on output | Keep as a comparison, not a safety-qualified replacement |
| V27 | Complete comparison 112/130 versus paired baseline 115/130; far-food case 1/5 | Reject |
| V28 | Frozen randomized comparison 123/130 versus paired V23 113/130; far-food C10b 5/5 versus 0/5 | Select for closed-loop investigation |

The key V28 wording separates a held UP from a goal: after a pickup, if the next real food is below, choose the downward intention. It keeps emergency retreat, real-food identification, current-row pickup priority, and safe pursuit above/below. Later version numbers are not automatically better policies; the release retains the selected candidate.

These preference measurements used the historical hop execution instructions. They are provenance for prompt development, not a 94.6% accuracy claim about the released direct-action game loop. The released prompt removes promises of automatic four-frame release and row-based reply filtering; [the exact adaptation](../artifacts/asterix/serial-selected/mechanics_prompt.diff) is retained.

## 3. Make the runtime match the research question

An early implementation added atomic four-frame hops, neutral landings, and rejection of replies captured before landing. That helped some development trajectories, but it also encoded movement decisions outside SOL. The user required raw model actions, so the selected runtime removed those rules.

With direct actions, a reply is held unchanged until a newer accepted reply replaces it. There is no automatic stop and no row-based filtering. An older sequence cannot replace a newer one; this is transport ordering. The human then proposed testing whether multiple overlapping observations encouraged repeated vertical movement. The next experiment reduced capacity to one and captured the next request only after the previous reply arrived.

## 4. Compare scheduling and public explanations

All four trials below used seed 5, a maximum 20 game seconds, 5× slowdown, fresh subscription replies, low effort, and direct actions. The ordered delay samples came from the same historical V16 valid-response profile and RNG seed. Different request schedules expose those samples at different game times. Each condition has one trial.

| Requests in flight | Output | Score | Endpoint |
|---:|---|---:|---|
| 8 | Action integer | 400 | Natural death at 14.67 game seconds |
| 8 | Action + brief English summary | 200 | Natural death at 15.53 game seconds |
| 1 | Action integer | 250 | 20 seconds, 1 life |
| **1** | **Action + brief English summary** | **500** | **20 seconds, 2 lives** |

Both serial trials survived longer; the action-only trial collected fewer points. This motivates the selected single-request configuration, rather than establishing a causal concurrency effect or general reliability. The public summary is the model's short explanation of its action, not a private reasoning trace or verified scene annotation.

For the selected condition, zero-model replay checked all 1,200 game frames and all 44 request image sets. A separate timing audit confirmed each new capture was at or after the previous reply's arrival. All 43 actions delivered before the horizon matched the model output exactly and remained held until a model replacement. The final outstanding reply was retained without being applied after the episode.

[Watch the selected 100-second replay with original music](../assets/asterix/v28-serial-english.mp4). The game panel is visually enhanced for presentation; actions, English summaries and timing are unchanged. Raw records and the original prompt/profile/source hashes live in [the selected campaign](../artifacts/asterix/serial-selected/).

## 5. Transfer to an actual clock

`sol simulate asterix` is development with historical sampled API delays. `sol eval asterix` uses a continuously advancing clock and actual subscription response time. The same direct action transport is used in both. The simulation's 500 points are not a real-time API result; native subscription timing is not ultrafast API timing. Fresh portable validation is recorded separately in [validation](validation.md).

The next research questions are repeated serial trials, additional seeds, long-tail sensitivity, missed food, and actual real-time performance. Each belongs in a new evaluation record rather than being inferred from this one successful clip.
