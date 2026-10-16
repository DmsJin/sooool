"""Shared structured decision schema; reported coordinates are audit-only."""
from __future__ import annotations

import hashlib
import json


def schema_hash(schema: dict | None) -> str | None:
    if schema is None:
        return None
    return hashlib.sha256(json.dumps(schema, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def grounded_schema(max_chunks: int = 3, max_duration: int = 48) -> dict:
    """Named action objects avoid ambiguity in fixed-width action arrays.

    Coordinates are the model's own visual estimates and must never feed an
    automatic controller. A null player represents an absent/dead player.
    """
    if type(max_chunks) is not int or not 1 <= max_chunks <= 4:
        raise ValueError('max_chunks must be an integer in 1..4')
    if type(max_duration) is not int or not 1 <= max_duration <= 120:
        raise ValueError('max_duration must be an integer in 1..120')
    def point():
        return {'type': 'array', 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2}
    action = {'type': 'object', 'additionalProperties': False,
              'required': ['move', 'shoot', 'focus', 'bomb', 'duration'],
              'properties': {
                  'move': {'type': 'integer', 'enum': list(range(9))},
                  'shoot': {'type': 'integer', 'enum': [0, 1]},
                  'focus': {'type': 'integer', 'enum': [0, 1]},
                  'bomb': {'type': 'integer', 'enum': [0, 1]},
                  'duration': {'type': 'integer', 'minimum': 1, 'maximum': max_duration}}}
    return {'type': 'object', 'additionalProperties': False,
            'required': ['player', 'boss', 'aim_x', 'plan'],
            'properties': {
                'player': {'anyOf': [point(), {'type': 'null'}]},
                'boss': point(), 'aim_x': {'type': 'number'},
                'plan': {'type': 'array', 'minItems': 1, 'maxItems': max_chunks, 'items': action}}}
