import unittest
from types import SimpleNamespace
from experiments.rhythm.model_env import ModelVisualEnv


class SensorFreshnessTest(unittest.IsolatedAsyncioTestCase):
    async def test_frame_delivered_during_clock_rpc_is_not_discarded(self):
        env = ModelVisualEnv('http://unused.invalid')
        old = {'png': b'old', 'capture_start_ms': 100, 'capture_end_ms': 100}
        fresh = {'png': b'fresh', 'capture_start_ms': 249.125, 'capture_end_ms': 249.125,
                 'raw_frame_timestamp_epoch_s': 123.456, 'time_origin_ms': 123206.875}
        env._latest_frame = old

        async def public_clock_rpc(expression):
            self.assertEqual(expression, 'performance.now()')
            # Represents a compositor event received during the browser RPC.
            env._latest_frame = fresh
            return 250

        env._page = SimpleNamespace(evaluate=public_clock_rpc)
        result = await env.capture()
        self.assertEqual(result['png'], b'fresh')
        self.assertEqual(result['capture_start_ms'], 249.125)
        self.assertEqual(result['capture_end_ms'], 249.125)
        self.assertEqual(result['raw_frame_timestamp_epoch_s'], 123.456)
        self.assertEqual(result['capture_staleness_ms'], .875)
        self.assertEqual(env._latest_frame, fresh)
        self.assertNotIn('capture_retrieved_ms', fresh)
