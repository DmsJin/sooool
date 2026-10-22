# DFJK Rhythm Lab

The selected setup plays the complete17-second preview excerpt with25 notes,
original1x audio and2.5-second visual approach. This is an original four-lane
practice environment, not the official game's chart or a full commercial song.
Use D/F/J/K. Judgment windows remain55/110/180ms; empty presses break combo.

From the repository root, run `uv run sol env setup rhythm` once.
Then use `sol simulate rhythm`, `sol profile rhythm` and
`sol eval rhythm`. See [the runnable workflow](../../docs/rhythm.md),
[autoresearch case study](../../docs/rhythm-autoresearch.md), and
[actual selected evidence](../../artifacts/rhythm/selected/result.json).

For manual play: `python3 -m http.server 8765 --bind 127.0.0.1 --directory dist`,
then open http://127.0.0.1:8765/?lang=en . The bundled excerpt avoids a network
fetch during play. Source preview/media provenance is documented at repo root.

The Gymnasium adapter is separate: `gym.make('DFJK-Rhythm-v0')` uses120Hz and
`MultiBinary(4)`. Its structured future-note observation is privileged and is
**never** passed to the visual policy. Browser/Gym default charts share the
selected25-note input. Music playback is in the browser, not Python Gym.
