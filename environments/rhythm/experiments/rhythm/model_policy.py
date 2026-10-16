"""Model-authored finite tap plans in an external monotonic clock domain.

No image interpretation, physical calibration, target lookup or time conversion
exists in this module. The executor receives precisely the model's numbers.
"""
import json
import math
import re

MAX_TAPS = 12
KEYS = frozenset(('d', 'f', 'j', 'k'))


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', value) is not None


def parse(answer):
    """Validate JSON schema only; never change any supplied command or time."""
    data = json.loads(answer)
    required = {'version', 'cancel_ids', 'taps'}
    if not isinstance(data, dict) or not required <= set(data) <= required | {'replace_pending'}:
        raise ValueError('Expected version, cancel_ids, taps and optional replace_pending')
    if 'replace_pending' in data and type(data['replace_pending']) is not bool:
        raise ValueError('replace_pending must be boolean; omission means false')
    version = data['version']
    if not _number(version) or not 0 <= version <= 2**53 - 1 or version % 1:
        raise ValueError('version must be a nonnegative safe integer')
    cancels = data['cancel_ids']
    if not isinstance(cancels, list) or len(cancels) > 12 or not all(_identifier(value) for value in cancels) or len(set(cancels)) != len(cancels):
        raise ValueError('cancel_ids must contain at most 12 unique valid identifiers')
    if not isinstance(data['taps'], list) or len(data['taps']) > MAX_TAPS:
        raise ValueError('taps must contain at most 12 commands')
    identifiers = set()
    for tap in data['taps']:
        if not isinstance(tap, dict) or set(tap) != {'id', 'key', 'at_ms', 'expires_ms'}:
            raise ValueError('Each tap requires exactly id, key, at_ms, expires_ms')
        if not _identifier(tap['id']) or tap['id'] in identifiers:
            raise ValueError('Tap identifiers must be nonempty and unique')
        if not isinstance(tap['key'], str) or tap['key'] not in KEYS:
            raise ValueError('key must be d, f, j or k')
        if not _number(tap['at_ms']) or not _number(tap['expires_ms']) or not 0 <= tap['at_ms'] <= tap['expires_ms']:
            raise ValueError('Tap timestamps must be finite and satisfy 0 <= at_ms <= expires_ms')
        identifiers.add(tap['id'])
    return data


def prompt(observation):
    """Whitelist policy-visible context; PNGs travel as separate image inputs."""
    frames = observation.get('frames', [])
    if not isinstance(frames, list) or not 1 <= len(frames) <= 3:
        raise ValueError('Expected one to three visual frames')
    metadata = []
    for frame in frames:
        start, end = frame['capture_start_ms'], frame['capture_end_ms']
        if not _number(start) or not _number(end):
            raise ValueError('Capture timestamps must be finite')
        metadata.append({'capture_start_ms': start, 'capture_end_ms': end})
    if not _number(observation['external_now_ms']):
        raise ValueError('External clock must be finite')
    context = {'frames': metadata, 'external_now_ms': observation['external_now_ms'],
               'pending_plans': observation.get('pending_plans', []),
               'executed_acks': observation.get('executed_acks', []),
               'rtt_history_ms': observation.get('rtt_history_ms', []),
               'request_version': observation.get('request_version', 0),
               'queue_version': observation.get('queue_version', 0),
               'model_memory': observation.get('model_memory', '')}
    return ("Play from these full-board screenshots, oldest first. Lanes left-to-right "
            "use d,f,j,k. Infer your own tap times from visual motion and interface. "
            "All capture/clock/ack/RTT times are external monotonic milliseconds; "
            "reason about request delay yourself. The executor uses your literal "
            "times without correction. Only supplied model-authored memory provides "
            "learned guidance; no chart is available. Return JSON only: "
            "{version:request_version,cancel_ids:[],taps:[{id,key,at_ms,expires_ms}]}. "
            "Optional replace_pending is boolean (default false); true replaces the "
            "pending plan. Choose your strategy using model memory. "
            "Use valid JSON quoted keys. At most 12 taps and "
            "12 unique cancel IDs. IDs: A-Z,a-z,0-9,_,-, length 1..64. Timestamps must "
            "be finite with 0<=at_ms<=expires_ms; choose expiry yourself. "
            "IDs identify intended taps; choose the ID strategy using model memory. To retain pending "
            "commands copy their IDs and literal times; cancel obsolete IDs yourself.\n"
            + json.dumps(context, separators=(',', ':'), allow_nan=False))
