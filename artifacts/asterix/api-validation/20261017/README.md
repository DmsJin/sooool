# Asterix: completed real-time API trials

Both games use V28, seed 5, `gpt-6.1-sol / low / ultrafast` via the OpenAI Responses API, one request in flight and direct model actions held unchanged until replaced. The game advances continuously at 12 raw FPS: 60 wall seconds = 720 frames = 12 game seconds (5× slowdown). No policy or executor changes separate the trials.

| Trial | Wall seconds | Score / lives | API calls | Usage cost (USD) | Legal-action median / max |
|---|---:|---|---:|---:|---|
| [First completed run](first-run/summary.json) | 60.001717 | 50 / 1 | 25 | 0.8909508 | 1.598s / 8.590s |
| [Repeat, featured video](repeat-run/summary.json) | 60.000341 | 300 / 2 | 31 | 1.1090868 | 1.487s / 2.747s |

All calls in both games have terminal usage and completed responses. Different model actions and arrival times produce different trajectories despite identical initial conditions. These two trials do not estimate reliability or establish which factor caused the score difference.

## Full video and evidence

[Full 60-second repeat replay](../../../../assets/asterix/v28-api-60s.mp4) · [Video provenance](../../../../assets/asterix/v28-api-60s.provenance.json) · [720-frame verification](../../../../assets/asterix/v28-api-60s.replay.json)

Each trial directory exposes its original summary, evaluation record, manifest, assessment and derived metrics. Its `evidence.tar.gz` retains the entire raw run, including the immutable source snapshot, original prompts/PNG inputs, public model outputs, safe transport metadata, actions, deliveries and per-frame rewards/lives. The archive SHA256 is recorded in `metrics.json`. Original source manifests and records have not been rewritten.

The video reconstructs saved actions at 12 FPS and verifies every frame's reward, cumulative score and lives. It has an original locally generated arcade soundtrack and game-panel color adjustment; the timeline, model actions and public summaries are unchanged. It is not an original screen capture. The README GIF is a continuous 50–60s excerpt; the full video is uncut.

For offline reproduction, extract `repeat-run/evidence.tar.gz`, then run from the repository root:

```bash
uv run python scripts/render_asterix_decisions.py \
  /path/to/asterix-realtime-approved-r2-20261017/seed-5 /tmp/asterix-repeat.mp4 --music
```

The frozen manifest identifies the run's own `source_snapshot`. The original freezer hashed historical profile JSONL files without copying them; `manifest-supplement/` now bundles hash-matching copies of those files alongside the unchanged original run. Every manifest source hash was checked against the archive. The current repository also retains the renderer. Rendering performs zero model calls.

## Cumulative accounting

The [new ledger](cumulative-ledger.json) has 67 settled requests: one probe, 25 first-game calls, 10 serial-profile samples and 31 repeat-game calls. Total new cost from reported usage is US$2.1357948. The [probe](probe/response.json) cost US$0.031986; the [serial profile](serial-profile/summary.json) cost US$0.1037712. The latter reused frozen inputs with 99.8% input-token cache hits and is not a gameplay result.

The [original failed request](../20261016/ledger.json) still has unknown actual usage and a US$0.27747 conservative reservation. Following explicit retry authorization, [budget conditions](budget-conditions.json) deducted that reservation from the original US$10 authorization, leaving the new ledger capped at US$9.72253. The old ledger was not reset or unblocked. The combined conservative commitment is US$2.4132648, below US$10. Costs are computed from reported usage by the retained client, rather than an independently reconciled invoice.
