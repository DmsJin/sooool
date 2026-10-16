# Optional evidence

Large retained research archives, trajectories and videos live on private evidence branches identified by each index entry. `index.jsonl` records every materializable artifact and its SHA256; large archives use verified parts. Retired policy records have been removed, so some historical archives and discussions are retained subsets. Current Asterix results are in `artifacts/asterix/serial-selected/`, with direct-eight-request comparisons beside them. `summaries/asterix-v28-development.json` describes the older Hop3 condition and is historical, not the selected default. Policy metadata in `policies/asterix/v28/` points to the active evidence.

```bash
python scripts/fetch_artifacts.py update-20261016-research.tar.gz --fetch
python scripts/unpack_artifacts.py artifacts/update-20261016-research.tar.gz --output /tmp/sol-evidence
```

Snapshots retain their original pre-redaction source hashes where available. Packaged hashes describe current files. Source account homes, credentials and hidden reasoning are excluded. Scores from other policies must not be attributed to the selected policy.
