"""Explicit paid Asterix transport; direct actions and fail-closed billing."""
import getpass
import json
import os
from pathlib import Path
from queue import Empty, SimpleQueue

from environments.touhou.research.api_client import ApiClient

SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'action': {'type': 'integer', 'minimum': 0, 'maximum': 8},
                   'reason': {'type': 'string', 'minLength': 1, 'maxLength': 400}},
    'required': ['action', 'reason'],
}


class AsterixApiClient:
    provider = 'openai_api'

    def __init__(self, *, key, ledger, budget, max_calls, output):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.events = SimpleQueue()
        self.calls = 0
        self.max_calls = max_calls
        limits = {'total_limit': str(budget), 'admission_limit': str(budget),
                  'stage_caps': {k: str(budget) for k in ('profile', 'reprofile', 'realtime')}}
        self.api = ApiClient(key, ledger, stage='realtime', max_output_tokens=512,
                             output_schema=SCHEMA, budget_limits=limits)

    def act(self, text, images, directory):
        from runner import parse_decision
        if self.calls >= self.max_calls:
            raise RuntimeError('API request limit reached; no additional request admitted')
        self.calls += 1
        directory.mkdir(parents=True, exist_ok=False)
        (directory/'prompt.txt').write_text(text)
        for i, image in enumerate(images):
            (directory/f'image-{i}.png').write_bytes(image)
        def validate(answer):
            parse_decision(answer, 'action_reason')
            return True
        def publish(result):
            action, reason = parse_decision(result['answer'], 'action_reason')
            self.events.put({'directory': directory.name, 'chosen': action, 'reason': reason,
                             'meta': result['meta']})
        try:
            result = self.api.decide(text, images, validate=validate, on_legal_action=publish)
            (directory/'response.json').write_text(json.dumps(result, indent=2)+'\n')
            return result['answer'], result['meta']
        except BaseException as exc:
            (directory/'failure.json').write_text(json.dumps({'type': type(exc).__name__})+'\n')
            raise

    def poll_action(self):
        try:
            return self.events.get_nowait()
        except Empty:
            return None

    def admitted_count(self):
        return len(self.api.ledger.snapshot()['requests'])

    def close(self):
        self.api.close()
        (self.output/'accounting.json').write_text(json.dumps(self.api.ledger.snapshot(), indent=2)+'\n')


def evaluate(root, recipe, out, args):
    import sys
    sys.path.insert(0, str(root/'environments/asterix'))
    from runner import run_recipe
    if recipe['output_format'] != 'action_reason':
        raise ValueError('Paid streaming evaluation requires action_reason output')
    key = os.environ.get('OPENAI_API_KEY') or getpass.getpass('OpenAI API key (process memory only): ')
    if not key:
        raise ValueError('A real API credential is required')
    ledger = args.ledger.resolve() if args.ledger else out/'ledger.json'
    try:
        return run_recipe(root, recipe, out, args,
            lambda output, system: AsterixApiClient(key=key, ledger=ledger, budget=args.budget_usd,
                                                  max_calls=args.max_calls, output=output), mode='realtime')
    finally:
        key = None
