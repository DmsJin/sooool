"""Lean field projection only; all decisions and tap times remain model-owned."""
import json

from .model_compact_policy import parse
from .model_policy import prompt as validated_observation_prompt

INSTRUCTION = (
    'Play screenshots oldest first; lanes left-right d,f,j,k. Use memory for '
    'reasoning and strategy. f=capture [start,end] ms; now=external monotonic ms; '
    'p=pending [id,key,at,expiry]; ack=raw receipts; rtt=raw request ms; '
    'v=request version. Return JSON {"v":v,"a":[[id,key,at_ms,expires_ms]]}, '
    'at most 12 rows; one when appropriate, [] otherwise. Times are literal: '
    'executor never corrects them. No scripts, expressions or conditions.\n'
)


def prompt(observation, *, include_rtt=True):
    validated = json.loads(validated_observation_prompt(observation).rsplit('\n', 1)[1])
    allowed_ack = ('id', 'status', 'key', 'at_ms', 'actual_ms')
    context = {'f': [[frame['capture_start_ms'], frame['capture_end_ms']] for frame in validated['frames']],
               'now': validated['external_now_ms'],
               'p': [[tap['id'], tap['key'], tap['at_ms'], tap['expires_ms']] for tap in validated['pending_plans']],
               'ack': [{key: receipt[key] for key in allowed_ack if key in receipt}
                       for receipt in validated['executed_acks'][-2:]],
               'rtt': validated['rtt_history_ms'][-4:],
               'v': validated['request_version']}
    instruction=INSTRUCTION
    if not include_rtt:
        context.pop('rtt')
        instruction=instruction.replace('rtt=raw request ms; ', '')
    return instruction + 'MODEL_AUTHORED_MEMORY:\n' + validated['model_memory'] + '\nOBSERVATION:\n' + json.dumps(context, separators=(',', ':'), allow_nan=False)
