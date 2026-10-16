# Optional evidence

Large retained research archives, trajectories and videos live on the private `codex/evidence` branch. `index.jsonl` records every materializable artifact and its SHA256; large archives use verified parts. Retired policy records have been removed, so some historical archives and discussions are retained subsets. Current Asterix development results are documented under `policies/asterix/v28/`.

```bash
python scripts/fetch_artifacts.py update-20261016-research.tar.gz --fetch
python scripts/unpack_artifacts.py artifacts/update-20261016-research.tar.gz --output /tmp/sol-evidence
```

Snapshots retain their original pre-redaction source hashes where available. Packaged hashes describe current files. Source account homes, credentials and hidden reasoning are excluded. Scores from other policies must not be attributed to the selected policy.
