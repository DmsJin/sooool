# Optional evidence

Large retained research archives, trajectories and videos live on private evidence branches identified by each index entry. `index.jsonl` records every materializable artifact and its SHA256; large archives use verified parts. Retired policy records have been removed, so some historical archives and discussions are retained subsets. Current Asterix development results are documented under `policies/asterix/v28/`.

```bash
python scripts/fetch_artifacts.py update-20261016-research.tar.gz --fetch
python scripts/unpack_artifacts.py artifacts/update-20261016-research.tar.gz --output /tmp/sol-evidence
```

Snapshots retain their original pre-redaction source hashes where available. Packaged hashes describe current files. Source account homes, credentials and hidden reasoning are excluded. Scores from other policies must not be attributed to the selected policy.

The selected Touhou v2 native English four-way live video lives on `codex/touhou-v2-evidence`. Keep this evidence branch while the index references it. Fetch and verify it with:

```bash
python scripts/fetch_artifacts.py videos/touhou-v2-english-fourway.mp4 --fetch
```

Small selected-action audits are in `touhou/records/`; full historical candidate inputs/responses remain in the original research workspace and are not included in this PR. Fresh full-game API validation of the new CLI is pending.
