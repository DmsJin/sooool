from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

from research.subscription import SubscriptionClient, LEAN_BASE_INSTRUCTIONS, LEAN_NATIVE_SETTINGS
from research.wire_schema import grounded_schema, schema_hash


class SchemaTest(unittest.TestCase):
    def test_closed_named_actions_and_bounds(self):
        schema = grounded_schema(3, 48)
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(set(schema['required']), {'player', 'boss', 'aim_x', 'plan'})
        plan = schema['properties']['plan']
        self.assertEqual((plan['minItems'], plan['maxItems']), (1, 3))
        action = plan['items']
        self.assertFalse(action['additionalProperties'])
        self.assertEqual(set(action['required']), set(action['properties']))
        self.assertEqual(action['properties']['duration']['maximum'], 48)
        self.assertEqual(action['properties']['move']['enum'], list(range(9)))
        self.assertEqual(schema['properties']['boss']['maxItems'], 2)
        self.assertIn({'type': 'null'}, schema['properties']['player']['anyOf'])

    def test_invalid_limits_and_stable_hash(self):
        for args in [(0, 48), (5, 48), (True, 48), (3, 0), (3, 121)]:
            with self.assertRaises(ValueError):
                grounded_schema(*args)
        schema = grounded_schema()
        self.assertEqual(schema_hash(schema), schema_hash(dict(reversed(list(schema.items())))))
        self.assertNotEqual(schema_hash(schema), schema_hash(grounded_schema(2)))
        self.assertIsNone(schema_hash(None))

    def test_native_turn_schema_is_optional_and_audited(self):
        requests = []
        class FakeBase:
            def _sandbox_command(self, workspace, runtime): return ['fake-native']
            def _initialize_session(self): self._rpc('thread/start', {}, None)
            def _read_lines(self, *args): pass
            def _rpc(self, method, params, *args):
                requests.append((method, params))
                if method == 'account/read': return {'account': {'type': 'chatgpt'}}, []
                if method == 'thread/start':
                    return {'model': 'gpt-6.1-sol', 'reasoningEffort': 'low',
                            'instructionSources': [], 'thread': {'id': 'fake'}}, []
                return {}, []
            def _request_action(self, prompt, images, directory):
                self._rpc('turn/start', {}, None)
                return '{}', {}
            def close(self):
                if self.runtime: self.runtime.cleanup()
        config = types.ModuleType('latency_bench.core.config')
        config.load_config = lambda path: {'policy': {}}
        codex = types.ModuleType('latency_bench.policy.codex')
        codex.CodexPolicyRunner = FakeBase
        with tempfile.TemporaryDirectory() as tmp, patch.dict(sys.modules, {
                'latency_bench.core.config': config, 'latency_bench.policy.codex': codex}), \
                patch('research.subscription.subprocess.Popen', return_value=Mock()) as popen, \
                patch('research.subscription.threading.Thread', return_value=Mock()):
            for index, (schema, lean) in enumerate([(None, False), (grounded_schema(), False), (grounded_schema(), True)]):
                start = len(requests)
                client = SubscriptionClient(Path(tmp), Path(tmp) / f'client{index}', schema, lean=lean)
                response = client.act('Return a decision', [b'\x89PNG\r\n\x1a\n'], Path(tmp) / f'decision{index}')
                turn = [p for m, p in requests if m == 'turn/start'][-1]
                self.assertEqual(turn.get('outputSchema'), schema)
                self.assertEqual(response['meta']['output_schema_sha256'], schema_hash(schema))
                self.assertEqual(turn['sandboxPolicy'], {'type': 'readOnly'})
                threads = [p for m, p in requests[start:] if m == 'thread/start']
                self.assertEqual(len(threads), 2)
                for thread in threads:
                    self.assertEqual(thread.get('baseInstructions'), LEAN_BASE_INSTRUCTIONS if lean else None)
                argv = popen.call_args.args[0]
                import json
                for key, value in LEAN_NATIVE_SETTINGS.items():
                    self.assertEqual(key + '=' + json.dumps(value) in argv, lean)
                self.assertEqual(response['meta']['lean_native'], lean)
                self.assertEqual(bool(response['meta']['base_instructions_sha256']), lean)
                client.close()


if __name__ == '__main__': unittest.main()
