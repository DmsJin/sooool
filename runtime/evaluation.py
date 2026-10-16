"""Append-only run records and explicit researcher decisions."""
import hashlib
import json
from pathlib import Path
import time


def record_run(out):
    out = Path(out)
    manifest = json.loads((out/'manifest.json').read_text())
    summary = json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else None
    row = {'schema_version':1, 'run':str(out), 'created_at_unix':time.time(),
        'game':manifest['game'], 'mode':manifest['mode'], 'recipe':manifest['recipe'],
        'manifest_sha256':hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest(),
        'summary':summary, 'status':'interrupted' if (out/'failure.json').exists() else 'completed' if summary is not None else 'incomplete',
        'performance_is_independently_confirmed':False}
    (out/'evaluation-record.json').write_text(json.dumps(row,indent=2)+'\n')
    return row


def assess(out, decision, note):
    out = Path(out).resolve()
    record = json.loads((out/'evaluation-record.json').read_text())
    row = {'created_at_unix':time.time(), 'run':str(out), 'decision':decision, 'note':note,
        'manifest_sha256':record['manifest_sha256'], 'mode':record['mode'], 'run_status':record['status']}
    with (out/'assessments.jsonl').open('a') as log:
        log.write(json.dumps(row)+'\n')
    return row
