# Gameplay highlights

Continuous excerpts from existing recordings. Original playback speed is retained. No new model calls. GIFs are silent; compact MP4 companions are included.

| Game | Source cut | GIF | MP4 | Public decision summary | Conditions |
|---|---|---|---|---|---|
| Rhythm | 2–10s of selected17s run | [GIF](rhythm.gif) | [MP4](rhythm.mp4) | Original English commentary | Actual native API1x,2.5s approach,24P/1Great/0Miss/2empty; MP4 includes complete17s excerpt plus2s results. GIF is silent. |
| Touhou | 49–56s | [GIF](touhou.gif) | [MP4](touhou.mp4) | Visible in original video | Source-harness realtime API, 1x; native English public decision summaries. |
| Pingpong | 20–32s | [GIF](pingpong.gif) | [MP4 excerpt](pingpong.mp4) · [Full match](../tabletennis/seed11-full.mp4) | Visible; original response, observation age and actual execution ID | Actual API, L1/seed 11, 1x, four model workers; tactical control, both camera views. Full match 5:1, uncut, including its failed point. The excerpt and full-match MP4 now include quiet locally generated background music; video streams and timing are unchanged. |
| Racing | 14–22s | [GIF](racing.gif) | [MP4](racing.mp4) | Visible in original video | Realtime API with coded steering, 1x; within original heat 2. Source video reordered heats win/loss/win, but this clip is continuous within a single heat. |
| Asterix | 50–60s of the full 60s run | [GIF](asterix.gif) | [MP4 excerpt](asterix.mp4) · [Full run](../asterix/v28-api-60s.mp4) | Original model-authored English summaries | Fresh Responses API, V28/seed 5, 12 raw FPS (5× slowdown); full run 300 points/two lives. Verified saved-action replay at original timing. GIF and compact excerpt are silent; full run has locally generated music. [Evidence](../../artifacts/asterix/api-validation/20261017/README.md). |
| Badminton | 6–21s | [GIF](badminton.gif) | [MP4](badminton.mp4) | Original English summaries from the same API responses as the tactical goals | Actual API, L1/seed 101, S3 slowdown. The 15s clip starts before the opening toss and continues through the serve and rally. Full match 8:11, 90/97 legal returns. Verified native replay; both camera views remain visible. The MP4 includes quiet locally generated background music; its video stream and timing are unchanged. |

Source paths, conditions and existing historical metadata are retained in [manifest.json](manifest.json). PingPong and Badminton recordings are identified by repository/run paths and source revisions. Original game logs and source snapshots remain unchanged.

Rebuild from local originals with `python3 scripts/build_readme_gifs.py` (Python 3 and ffmpeg required). The Rhythm, PingPong, Badminton and Asterix source videos are bundled; Touhou and Racing manifest sources retain historical absolute machine paths, which must be remapped to the matching originals when rebuilding elsewhere. Playback speed means speed relative to each source recording, not a claim that every game runs at native 1×.
The current PingPong source video is included in the repository; rebuild just its
preview with `python3 scripts/build_readme_gifs.py --game pingpong`.
For Rhythm, `--game rhythm` rebuilds only the GIF from the retained complete
`rhythm.mp4`; it preserves that source video and its audio. The current Rhythm
policy emits absolute tap timestamps; the retired coordinate-to-time campaign
is retained only as historical research.

Rebuild the Badminton GIF with `python3 scripts/build_readme_gifs.py --game badminton`
from the bundled music MP4; this preserves its source video and audio.
The original is 1440×800 at 100/3 FPS. The preview and compact MP4 sample 12 FPS
at 960 pixels wide, with the same 15-second duration and S3 playback speed.
The first observed toss is at physics frame 220, the serve travels toward the
opponent by frame 300, and a return reaches
SOL by frame 400. The opening point eventually ends 1:0 outside this short cut.
See [Badminton evidence](../../artifacts/badminton/README.md) for the complete-match
protocol and audit. Full original media and logs remain in the recorded `outputs/`
directory and are not required to play the committed short clip.

These excerpts contain no frame reordering or speed changes within a clip. The builder samples frames, optionally crops, scales proportionally and converts GIF palettes. PingPong's complete video is rendered offline from every recorded native pose on the measured live wall clock, with the side camera continuously visible. It is not a screen capture. The orange ball ring/trail is an offline visibility aid, including through occlusion. Its latest public summary may describe an older observation; `NEXT` and the actually executing reply are distinct. Racing uses coded steering. Public decision summaries are model-authored outputs, not internal reasoning transcripts.

PingPong and Badminton MP4 background music was generated locally with the original procedural arcade composer; no external recordings or samples were used. Music fades in/out and targets −24 LUFS. [Music provenance and unchanged-video packet hashes](sports-music-provenance.json) identify the originals by immutable commit. GIFs remain silent. Both highlights now rebuild from their bundled music MP4s at `start_seconds: 0`; `original_source` and `original_start_seconds` preserve the original 20–32s PingPong and 6–21s Badminton cuts. The rebuild preserves the source MP4 and its audio.
