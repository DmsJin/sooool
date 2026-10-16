# Gameplay highlights

Continuous excerpts from existing recordings. Original playback speed is retained. No new model calls. GIFs are silent; compact MP4 companions are included.

| Game | Source cut | GIF | MP4 | Public decision summary | Conditions |
|---|---|---|---|---|---|
| Rhythm | 23–31s | [GIF](rhythm.gif) | [MP4](rhythm.mp4) | Pending; gameplay only | Native browser/audio API capture, 1x; episode 03. GIF is silent. |
| Touhou | 49–56s | [GIF](touhou.gif) | [MP4](touhou.mp4) | Visible in original video | Source-harness realtime API, 1x; native English public decision summaries. |
| Pingpong | 234–246s | [GIF](pingpong.gif) | [MP4](pingpong.mp4) | Pending; gameplay only | Replay of recorded final 5:2 API match at official S=10 slowdown; cropped spectator view. Not a live screen capture; review pauses omitted in source export. |
| Racing | 14–22s | [GIF](racing.gif) | [MP4](racing.mp4) | Visible in original video | Realtime API with coded steering, 1x; within original heat 2. Source video reordered heats win/loss/win, but this clip is continuous within a single heat. |
| Asterix | 60–70s | [GIF](asterix.gif) | [MP4](asterix.mp4) | Visible in original video | Historical sampled-delay simulation replay, 5x slowdown; V28 serial direct actions with original public English decision summaries. Source playback speed retained. |

Source paths and SHA256 hashes are retained in [manifest.json](manifest.json). Original recordings remain unchanged.

Rebuild from local originals with `python3 scripts/build_readme_gifs.py` (Python 3 and ffmpeg required). Adjust source paths in the manifest if needed.

These excerpts contain no frame reordering or speed changes within a clip. The builder samples frames, optionally crops, scales proportionally and converts GIF palettes. PingPong is a cropped spectator replay at official S=10 with review pauses omitted in the source export. Racing uses coded steering. Public decision summaries are model-authored outputs, not internal reasoning transcripts.
