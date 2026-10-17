"""Explicit paid Asterix transport; direct actions and fail-closed billing."""
import getpass
import json
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import sys

# Console scripts place .venv/bin on sys.path, unlike `python -m` and root tests.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from environments.touhou.research.api_client import ApiClient

SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'action': {'type': 'integer', 'minimum': 0, 'maximum': 8},
                   'reason': {'type': 'string', 'minLength': 1, 'maxLength': 400}},
    'required': ['action', 'reason'],
}


class DiagnosticSession:
    """Retain allowlisted transport metadata; never keys, raw bodies or reasoning."""
    def __init__(self, session):
        self.session = session
        self.directory = None

    def post(self, *args, **kwargs):
        response = self.session.post(*args, **kwargs)
        return DiagnosticResponse(response, self.directory)

    def close(self):
        self.session.close()


class DiagnosticResponse:
    def __init__(self, response, directory):
        self.response, self.directory = response, directory
        self.status_code = response.status_code
        self.headers = response.headers
        self.record = {'http_status': response.status_code,
                       'provider_request_id': response.headers.get('x-request-id'),
                       'event_counts': {}, 'response_metadata': []}

    def __enter__(self):
        self.response.__enter__()
        return self

    def __exit__(self, *args):
        try:
            (self.directory/'transport.json').write_text(json.dumps(self.record, indent=2)+'\n')
        finally:
            self.response.__exit__(*args)

    def iter_lines(self, **kwargs):
        for raw in self.response.iter_lines(**kwargs):
            if raw and raw.startswith(b'data:'):
                try:
                    event = json.loads(raw[5:].strip())
                except (ValueError, UnicodeError):
                    event = {}
                kind = event.get('type')
                if isinstance(kind, str):
                    counts = self.record['event_counts']
                    counts[kind] = counts.get(kind, 0)+1
                if kind in ('response.created','response.completed','response.failed','response.incomplete','error'):
                    response = event.get('response') or {}
                    row = {k: response[k] for k in ('id','status','model','service_tier','usage') if k in response}
                    row['event_type'] = kind
                    error = response.get('error') or event.get('error') or event
                    row['error_code'] = error.get('code') if isinstance(error,dict) else None
                    self.record['response_metadata'].append(row)
            yield raw


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
        import requests
        self.session = DiagnosticSession(requests.Session())
        self.api = ApiClient(key, ledger, stage='realtime', max_output_tokens=512,
                             output_schema=SCHEMA, budget_limits=limits, session=self.session)

    def act(self, text, images, directory):
        from runner import parse_decision
        if self.calls >= self.max_calls:
            raise RuntimeError('API request limit reached; no additional request admitted')
        self.calls += 1
        directory.mkdir(parents=True, exist_ok=False)
        self.session.directory = directory
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
            failure={'type':type(exc).__name__}
            if isinstance(getattr(exc,'diagnostics',None),dict):failure['diagnostics']=exc.diagnostics
            (directory/'failure.json').write_text(json.dumps(failure,indent=2)+'\n')
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
