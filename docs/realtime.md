# Real-time evaluation

## Asterix

```bash
uv run sol eval asterix --seed 5 --duration 20 --output runs/asterix-realtime
```

This uses actual ChatGPT subscription inference and a continuously advancing 12-raw-FPS clock (5× slowdown). One request is in flight; complete model actions are held unchanged until replaced. Game time continues while the model computes. There is no automatic hop release, neutral landing or row-based filtering. A completed response is applied on the next game tick; the next observation is captured at the next four-frame observation tick.

`sol simulate asterix` uses the same policy/action semantics but samples a historical API delay profile and pauses native computation outside virtual game time. The default 500-point demonstration is profile development evidence. The realtime command measures subscription latency and game performance; it is not a paid ultrafast API calibration or native-speed result.

Each trial retains the exact task, model public output, capture frame, delivery frame, actual capture-to-apply duration, frame lag, applied action, rewards/lives, source snapshot and evaluation record. Interrupted calls preserve partial artifacts; authentication failures cannot fall back to paid API. The default quota stop is 80%. Record retain/reject decisions with `sol record`; see [the recording protocol](evaluation-records.md).

A paid ultrafast API trial requires the user's own secure credentials, explicit per-run spending budget, complete-response and early-action calibration, failure/usage accounting, and fresh real-time validation. The original API research utilities remain available at [the fixed Asterix source checkpoint](https://github.com/sooool-project/sooool/tree/053545c1c27e6beccb80598e7a4d57f80865afc1/research/asterix/realtime-source). This release does not expose an unvalidated paid API launcher or inherit an old budget authorization.

## Other games

Rhythm and Touhou retain their original real-time research paths:

- Rhythm model-owned timing: `environments/rhythm/experiments/rhythm/model_native.py`; prior cropped-coordinate campaign: `realtime_v2.py`. Native audio evaluation additionally needs the authorized audio resource and continuous audio/browser clocks.
- Touhou: `environments/touhou/research/run_episode.py` with `provider=api`, `mode=realtime`; direct API schema/early-action logic lives in `api_client.py`.

Their original commands retain their declared resource and budget assumptions. The new root `sol eval` command currently supports Asterix. Historical and fresh results must remain separately labeled.
