# Gameplay highlights

Continuous excerpts from existing recordings. Original playback speed is retained. No new model calls. GIFs are silent; compact MP4 companions are included.

| Game | Source cut | GIF | MP4 | Public decision summary | Conditions |
|---|---|---|---|---|---|
| Rhythm | 2–10s of selected17s run | [GIF](rhythm.gif) | [MP4](rhythm.mp4) | Original English commentary | Actual native API1x,2.5s approach,24P/1Great/0Miss/2empty; MP4 includes complete17s excerpt plus2s results. GIF is silent. |
| Touhou | 49–56s | [GIF](touhou.gif) | [MP4](touhou.mp4) | Visible in original video | Source-harness realtime API, 1x; native English public decision summaries. |
| Pingpong | 20–32s | [GIF](pingpong.gif) | [MP4 excerpt](pingpong.mp4) · [Full match](../tabletennis/seed11-full.mp4) | Visible; original response, observation age and actual execution ID | Actual API, L1/seed 11, 1x, four model workers; tactical control, both camera views. Full match 5:1, uncut, including its failed point. |
| Racing | 14–22s | [GIF](racing.gif) | [MP4](racing.mp4) | Visible in original video | Realtime API with coded steering, 1x; within original heat 2. Source video reordered heats win/loss/win, but this clip is continuous within a single heat. |
| Asterix | 60–70s | [GIF](asterix.gif) | [MP4](asterix.mp4) | Visible in original video | Historical sampled-delay simulation replay, 5x slowdown; V28 serial direct actions with original public English decision summaries. Source playback speed retained. |

Source paths, conditions and existing historical metadata are retained in [manifest.json](manifest.json). The new PingPong recording is identified by its repository/run path and source revision. Original game logs and source snapshots remain unchanged.

Rebuild from local originals with `python3 scripts/build_readme_gifs.py` (Python 3 and ffmpeg required). Adjust source paths in the manifest if needed.
The current PingPong source video is included in the repository; rebuild just its
preview with `python3 scripts/build_readme_gifs.py --game pingpong`.

These excerpts contain no frame reordering or speed changes within a clip. The builder samples frames, optionally crops, scales proportionally and converts GIF palettes. PingPong's complete video is rendered offline from every recorded native pose on the measured live wall clock, with the side camera continuously visible. It is not a screen capture. The orange ball ring/trail is an offline visibility aid, including through occlusion. Its latest public summary may describe an older observation; `NEXT` and the actually executing reply are distinct. Racing uses coded steering. Public decision summaries are model-authored outputs, not internal reasoning transcripts.
