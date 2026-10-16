# PingPong tactical evidence

These are complete **actual API** matches, not sampled-delay simulation. Both
used L1, a 1x target, native 100 Hz physics, 20 Hz public camera/rule control,
two asynchronous native planning processes and four staggered model workers
(0.65 s request interval). Model: GPT-6.1 Sol, Low, Ultrafast.

| Seed | Score | Legal own serves | Legal returns | Native / wall seconds | Calls / API cost |
| --- | --- | --- | --- | --- | --- |
| 11 | 5:1 | 4/4 | 6/7 | 31.29 / 31.588 | 47 / $1.495302 |
| 12 | 3:5 | 3/4 | 5/9 | 36.04 / 36.390 | 52 / $1.6429482 |

The seed-11 win still has one out-of-bounds return. Seed 12 has three missed
contacts on opponent serves, one own-half return fault and one own service fault.
Its longest sequence is two consecutive legal returns, followed by the own-half
fault. These two seeds do not establish stable serving, long rallies or a win rate.
The model selects persistent shot policies; the rule controller owns serving,
tracking and joint motion. This is hierarchical tactical control.

The gameplay code and all run configuration except seed match between the two
matches. Their original summaries are retained as [seed11-summary.json](seed11-summary.json)
and [seed12-summary.json](seed12-summary.json). The [seed-12 validation](seed12-validation.json)
retains reply-to-stroke bindings, per-contact diagnostics and display alignment.
Every one of the 7 seed-11 and 9 seed-12 installed return-flight strategies
references an accepted model reply; policy fallback was zero in both matches.

## Video and public summaries

[Complete seed-11 match](../../assets/tabletennis/seed11-full.mp4): 1920x1080,
50 FPS, both behind and side cameras throughout, measured live wall time plus
a one-second final hold. It is an offline native-pose render, not a screen capture.
The orange ball ring/trail is an offline visibility aid, including through occlusion.
The [README excerpt](../../assets/gameplay/README.md) is 20–32 s, without speed changes.

Public summaries come verbatim from the same model response as the policy.
The large text is the latest accepted summary of its labeled, older observation.
`NEXT` and the strategy actually executing are displayed separately because a
committed flight cannot change policy. Four workers improve throughput, not the
roughly two-second age of an individual reply. Seed-12 export checked all 1,870
frames: no summary appears before acceptance; acceptance-to-display quantization
is at most 19.4 ms. Model interpretations remain estimates, not certified facts.

## Original records

Server workspace: `/home/ubuntu/lzj/sooool-pingpong-tactical`.

- `runs/tabletennis/api-ultrafast-rally-mw4-s1-001`
- `runs/tabletennis/api-ultrafast-rally-mw4-s1-seed12-001`

Each run retains its frozen `source_snapshot`, requests, receipts, public camera
images, native poses, planning/application logs and budget snapshots. Their
repository base was `bf6428147e4253a6eae1d3822eb87a8f492ac8e0`; the uncommitted
implementation is captured by those source snapshots. Later offline replay
styling is separate from gameplay. Runtime native copy:
`/home/ubuntu/auto-research/deps/latency-bench/third_party/roboolympics`, recipe
revision `da1f787f775ea6524d698c0b063157ded4c0fef9` (deployment has no Git metadata).

Earlier development runs and detailed diagnostic reports remain on the server.
The previous S=10 direct-action demo and research source remain in Git history
and the research archive. They are not the current controller or comparable timing.
