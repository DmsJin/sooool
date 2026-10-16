"""Compact wire syntax for the model's literal additive tap commands."""
import json

from .model_policy import parse as validate_canonical
from .model_policy import prompt as validated_observation_prompt

INSTRUCTION = (
    'Play from the screenshots, oldest first; lanes left-right use d,f,j,k. '
    'Use model_memory to choose visual reasoning, timing and IDs. Times are '
    'literal external monotonic milliseconds; the executor never corrects them. '
    'Return JSON only: {"v":request_version,"a":[[id,key,at_ms,expires_ms]]}. '
    'Prefer one row when appropriate; a=[] otherwise. At most 12 rows. '
    'No expressions, scripts, conditions, cancellation or replacement.\n'
)


def prompt(observation):
    # Reuse precisely the existing validated observation whitelist. Its static
    # instruction text is discarded; only its JSON context is carried forward.
    context = validated_observation_prompt(observation).rsplit('\n', 1)[1]
    return INSTRUCTION + context


def parse(answer):
    wire = json.loads(answer)
    if not isinstance(wire, dict) or set(wire) != {'v', 'a'}:
        raise ValueError('Expected exactly v and a')
    if not isinstance(wire['a'], list) or len(wire['a']) > 12:
        raise ValueError('Expected at most 12 tap rows')
    taps = []
    for row in wire['a']:
        if not isinstance(row, list) or len(row) != 4:
            raise ValueError('Tap rows must contain exactly id,key,at_ms,expires_ms')
        taps.append({'id': row[0], 'key': row[1], 'at_ms': row[2], 'expires_ms': row[3]})
    canonical = {'version': wire['v'], 'cancel_ids': [], 'taps': taps, 'replace_pending': False}
    # Schema validation only: no numbers, identifiers, or expiry values change.
    return validate_canonical(json.dumps(canonical, allow_nan=False))
