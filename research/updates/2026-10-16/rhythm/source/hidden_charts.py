"""TRUSTED evaluator-only held-out charts, generated after a policy freeze.

Do not import this module in a policy worker or mount its private output there.
Only public_metadata() is suitable for publishing; even that is not an actor
observation. Seeds, files and notes belong exclusively to the trusted renderer.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import secrets


@dataclass(frozen=True)
class HiddenChart:
    chart_path: Path = field(repr=False)
    seed_path: Path = field(repr=False)
    metadata: dict = field(repr=False)

    def public_metadata(self):
        return dict(self.metadata)


def _private_write(path, payload):
    with path.open('xb') as handle:
        handle.write(payload)
    path.chmod(0o600)


def generate(private_dir, freeze_manifest, *, model_workspace=None,duration=30.000998):
    """Read a frozen manifest first; only then sample a fresh secret seed.

    model_workspace, if supplied, is the host path mounted into the policy
    worker. Refuse placing evaluator evidence underneath that directory.
    """
    if not math.isfinite(duration) or not 8<=duration<=30.000998:
        raise ValueError('duration must be 8..30.000998 seconds')
    freeze_manifest = Path(freeze_manifest)
    freeze_bytes = freeze_manifest.read_bytes()
    if not freeze_bytes:
        raise ValueError('A nonempty policy freeze must exist before generation')
    # Fail early for accidental invalid/unfinished manifests.
    frozen = json.loads(freeze_bytes)
    if not isinstance(frozen, dict) or not frozen:
        raise ValueError('Policy freeze must be a nonempty JSON object')
    private_dir = Path(private_dir).resolve()
    if model_workspace is not None:
        workspace = Path(model_workspace).resolve()
        if private_dir == workspace or workspace in private_dir.parents:
            raise ValueError('Hidden charts cannot be stored in the model workspace')
    private_dir.mkdir(parents=True, exist_ok=True)
    private_dir.chmod(0o700)
    seed = secrets.token_bytes(32)  # Deliberately AFTER freeze reading/validation.
    rng = random.Random(int.from_bytes(seed, 'big'))
    beat = 60 / 113
    phase = rng.random() * beat
    quarters = [phase + index * beat for index in range(64)
                if 2 <= phase + index * beat <= 29.3]
    eighths = [value + beat / 2 for value in quarters if value + beat / 2 <= 29.3]
    positions = [(value, 4) for value in rng.sample(quarters, 40)]
    positions += [(value, 8) for value in rng.sample(eighths, 12)]
    notes = [{'time': round(value, 6), 'lane': rng.randrange(4), 'subdivision': subdivision}
             for value, subdivision in sorted(positions)]
    if duration<30.000998:
        notes=[note for note in notes if note['time']<=duration-.7]
    chart = {'title': 'Held-out visual rhythm challenge', 'artist': 'Rick Astley',
             'difficulty': 1, 'bpm': 113, 'duration': duration,
             'source': 'Apple official preview; newly randomized held-out visual chart',
             'beat_phase': phase, 'chart_version': 'heldout-secret-v1', 'notes': notes}
    chart_bytes = json.dumps(chart, sort_keys=True, separators=(',', ':')).encode()
    chart_sha = hashlib.sha256(chart_bytes).hexdigest()
    seed_commitment = hashlib.sha256(seed).hexdigest()
    tag = secrets.token_hex(8)
    chart_path = private_dir / f'{tag}.chart.json'
    seed_path = private_dir / f'{tag}.seed'
    _private_write(chart_path, chart_bytes)
    _private_write(seed_path, seed.hex().encode())
    metadata = {'chart_sha256': chart_sha, 'seed_commitment': seed_commitment,
                'policy_freeze_sha256': hashlib.sha256(freeze_bytes).hexdigest(),
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'difficulty': 1, 'duration_s': chart['duration'], 'note_count': len(notes),
                'generation': 'fresh_secret_seed_after_policy_freeze', 'heldout': True}
    _private_write(private_dir / f'{tag}.evidence.json', json.dumps(metadata, indent=2).encode())
    return HiddenChart(chart_path, seed_path, metadata)
