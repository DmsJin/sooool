# Real-time API path

The current unified `sol simulate` entrypoint uses a ChatGPT subscription and imposed profile timing. It is not the real-time API path.

Original real-time implementations are preserved:

- Rhythm model-owned timing: `environments/rhythm/experiments/rhythm/model_native.py`; prior cropped-coordinate campaign: `realtime_v2.py`. These are distinct policies. A real-time run also needs the authorized preview audio, and continuous native audio/browser clocks.
- Touhou: `environments/touhou/research/run_episode.py` with `provider=api`, `mode=realtime`; direct API schema/early-action logic lives in `api_client.py`.
- Asterix V28 currently uses the profile simulation launcher. Retained budget/profiling utilities are under `research/asterix/realtime-source/`; a portable direct-API driver for the selected policy remains unvalidated.

The original commands have machine-specific dependency/resource and budget-ledger assumptions. They are research source, not yet a validated universal `sol eval` command. Do not reuse an old ledger's budget authorization for a new user. A future portable direct-API launcher must take the user's own process-only credentials and explicit per-run budget, preserve uncertain reservations, and verify the full continuously advancing game path. No paid API call was made during package validation.

Subscription protocol reference: [official Codex app-server documentation](https://learn.chatgpt.com/docs/app-server). The runtime authenticates via an existing ChatGPT sign-in and fails closed on API-only authentication; it never switches to a paid provider.
