import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from research.api_client import ApiClient
from research.budget import BudgetLedger, reservation_usd


class MockResponse:
    status_code = 200
    def __init__(self, refusal=False, incomplete=False):
        self.refusal = refusal
        self.incomplete = incomplete
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def iter_lines(self, **kwargs):
        if self.refusal:
            yield b'data: {"type":"response.refusal.delta","delta":"refused"}'
        else:
            yield b'data: {"type":"response.output_text.delta","delta":"{\\"actions\\":[]}"}'
        terminal = 'response.incomplete' if self.incomplete else 'response.completed'
        response = {'model': 'gpt-6.1-sol', 'service_tier': 'ultrafast',
                    'usage': {'input_tokens': 20, 'output_tokens': 10}}
        yield b'data: ' + json.dumps({'type': terminal, 'response': response}).encode()


class MockSession:
    def __init__(self, **kwargs): self.kwargs = kwargs;self.calls = []
    def post(self, *args, **kwargs):
        self.calls.append(kwargs)
        return MockResponse(**self.kwargs)


class StructuredClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = str(Path(self.temp.name) / 'ledger.json')
        self.png = b'\x89PNG\r\n\x1a\n' + b'\0' * 8 + (640).to_bytes(4, 'big') + (480).to_bytes(4, 'big')
        self.schema = {'type': 'object', 'properties': {'actions': {'type': 'array', 'items': {'type': 'integer'}}}, 'required': ['actions'], 'additionalProperties': False}
    def tearDown(self): self.temp.cleanup()

    def test_payload_schema_hash_and_reservation_include_schema(self):
        session = MockSession()
        client = ApiClient('not-a-real-key', self.ledger, session=session, output_schema=self.schema)
        result = client.decide('observe', [self.png])
        schema_text = json.dumps(self.schema, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        self.assertEqual(session.calls[0]['json']['text']['format'], {'type': 'json_schema', 'name': 'touhou_grounded_plan', 'strict': True, 'schema': self.schema})
        expected_hash = hashlib.sha256(schema_text.encode()).hexdigest()
        self.assertEqual(result['meta']['shape']['schema_sha256'], expected_hash)
        row = next(iter(BudgetLedger(self.ledger).snapshot()['requests'].values()))
        self.assertEqual(row['reserved_usd'], str(reservation_usd('observe' + schema_text, 1, 128)))
        self.assertGreater(reservation_usd('observe' + schema_text, 1, 128), reservation_usd('observe', 1, 128))

    def test_forecast_api_order_matches_native_without_changing_legacy_default(self):
        from research.wire_schema import decision_schema
        schema=decision_schema('tracking_dodge_forecast_v9',1,48)
        session=MockSession()
        result=ApiClient('not-a-real-key',self.ledger,session=session,output_schema=schema,preserve_schema_order=True).decide('observe',[self.png])
        wire=session.calls[0]['json']['text']['format']['schema']
        self.assertEqual(list(wire['properties']),list(schema['properties']))
        self.assertEqual(list(wire['properties']['forecast']['properties']),['boss_vx_px_s','player_at_apply','endpoint','boss_at_shot_x'])
        self.assertEqual(result['meta']['shape']['schema_order_sha256'],hashlib.sha256(json.dumps(wire,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())
        old=ApiClient('not-a-real-key',self.ledger,session=MockSession(),output_schema=schema)
        self.assertEqual(list(old.output_schema['properties']),sorted(schema['properties']))
        self.assertEqual(old.schema_text,json.dumps(schema,sort_keys=True,separators=(',',':'),ensure_ascii=False))

    def test_output_cap_512_is_reserved_and_transmitted(self):
        session = MockSession()
        client = ApiClient('not-a-real-key', self.ledger, session=session, max_output_tokens=512)
        result = client.decide('observe', [self.png])
        self.assertEqual(session.calls[0]['json']['max_output_tokens'], 512)
        row = next(iter(BudgetLedger(self.ledger).snapshot()['requests'].values()))
        self.assertEqual(row['reserved_usd'], str(reservation_usd('observe', 1, 512)))
        self.assertGreater(reservation_usd('observe', 1, 512), reservation_usd('observe', 1, 256))

    def test_output_cap_bounds_fail_before_paid_work(self):
        for cap in (15, 513, True, 512.0):
            with self.assertRaises(ValueError):
                ApiClient('not-a-real-key', self.ledger, session=MockSession(), max_output_tokens=cap)
        self.assertFalse(Path(self.ledger).exists())

    def test_legacy_payload_unchanged_when_schema_omitted(self):
        session = MockSession()
        result = ApiClient('not-a-real-key', self.ledger, session=session).decide('observe', [self.png])
        self.assertNotIn('text', session.calls[0]['json'])
        self.assertNotIn('schema_sha256', result['meta']['shape'])

    def test_refusal_settles_usage_and_stops_without_retry(self):
        session = MockSession(refusal=True)
        client = ApiClient('not-a-real-key', self.ledger, session=session, output_schema=self.schema)
        with self.assertRaisesRegex(RuntimeError, 'refused'):
            client.decide('observe', [self.png])
        row = next(iter(BudgetLedger(self.ledger).snapshot()['requests'].values()))
        self.assertEqual(row['status'], 'settled')
        self.assertEqual(len(session.calls), 1)

    def test_incomplete_settles_usage_without_retry(self):
        session = MockSession(incomplete=True)
        client = ApiClient('not-a-real-key', self.ledger, session=session, output_schema=self.schema)
        with self.assertRaisesRegex(RuntimeError, 'without completion'):
            client.decide('observe', [self.png])
        self.assertEqual(next(iter(BudgetLedger(self.ledger).snapshot()['requests'].values()))['status'], 'settled')
        self.assertEqual(len(session.calls), 1)


if __name__ == '__main__': unittest.main()
