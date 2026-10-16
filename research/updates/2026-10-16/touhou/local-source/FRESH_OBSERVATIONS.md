# Optional fresh captures with spaced visual history

The default observation path is unchanged: capture every `image_stride` visual
frames (or `decision_stride` if omitted), retaining the last `history_frames`
captures in their existing deque order. Existing valid configs and prompt/schema
definitions keep their behavior.

An opt-in episode configuration can separate a fresh latest image from history:

```json
{
  "decision_stride": 6,
  "image_stride": 30,
  "capture_stride": 6,
  "history_frames": 3,
  "history_spacing_frames": 30
}
```

`capture_stride` overrides only the visual capture interval. A request is still
subject to `decision_stride`, capacity and the existing winner/movement gates;
this does not make the model or API respond every six frames. Under realtime,
the explicit override schedules the next capture from the atomic capture's own
visual timestamp rather than an older loop timestamp.

`history_spacing_frames` is measured in logical physics frames. For each older
target (`latest - spacing`, `latest - 2*spacing`), the selector uses the latest
available captured image at or before that target. At logical frame72 with
six-frame captures and spacing30, input frames are `[12,42,72]`. Irregular capture
gaps may yield wider/nonuniform intervals; the model sees their actual frame
numbers. No image is synthesized, relabeled or taken from the future.

The latest original PNG is always included. With insufficient past history, send
fewer images; never duplicate one old picture to fill a slot. Startup progresses
from one image to two and then three as enough logical history is observed.
While a declaration pauses physics, repeated captures at the same logical frame
replace that frame's picture with the newest capture. This prevents an animation
pause from becoming several apparent velocity samples. This deduplication is
opt-in; with neither new option, the original deque is retained exactly.

`capture_stride` alone keeps the last up-to-three distinct captures without
forcing spacing. `history_spacing_frames` alone keeps the existing capture
cadence. Both options must be positive integer frame counts; `history_frames`
must be an integer in1..3. Storage retains the requested logical span and one
older bracketing sample, deduplicating repeated clocks.

Only `(observed logical frame, original PNG)` enters the selector. Actor task
instructions, action schema, scheduler policy, game/Gym state and rewards are
unchanged. No motion estimate, entity state, action choice or hidden timing is
added. This is preparation for a separately authorized cadence experiment, not
an empirical speed/quality claim: only unit tests and a mock episode loop ran.
