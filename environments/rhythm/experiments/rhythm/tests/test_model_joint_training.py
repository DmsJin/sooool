import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from experiments.rhythm.model_joint_training import load_joint_delays, run_episode


class JointTrainingTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_pixels_and_literal_delivery_are_causal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            profile = path / 'joint.json'
            profile.write_text(json.dumps({'rows': [{'status': 'completed', 'api_rtt_s': .1,
                                'frame_age_s': .2, 'transport_overhead_s': .15}]}))
            calls, applies, captures = [], [], []

            class Env:
                def __init__(self, *a, **kw): self.t = 0
                async def __aenter__(self): return self
                async def __aexit__(self, *a): pass
                async def start(self): pass
                async def advance(self, t):
                    self.assert_monotonic(t)
                    self.t = t
                def assert_monotonic(self, t):
                    if t < self.t: raise AssertionError('rewind')
                async def capture(self):
                    captures.append(self.t)
                    return {'png': str(self.t).encode(), 'capture_start_ms': 10000+self.t*1000,
                            'capture_end_ms': 10000+self.t*1000, 'private_chart': 'PRIVATE_SENTINEL'}
                async def snapshot(self):
                    return {'clock_ms': 10000+self.t*1000, 'version': 0, 'pending': [],
                            'rawacks': [], 'secret_notes': 'PRIVATE_SENTINEL'}
                async def apply(self, plan):
                    applies.append((self.t, plan))
                    return {'clock_ms': 10000+self.t*1000, 'transaction_status': 'accepted'}
                async def trusted_evaluator(self):
                    return {'state': 'result' if self.t >= .9 else 'playing', 'judged': 52,
                            'total_notes': 52, 'counts': {'perfect': 52, 'miss': 0}}

            class Provider:
                async def start(self): return self
                async def close(self): pass
                async def act(self, text, images):
                    self.context = json.loads(text.rsplit('\n', 1)[1])
                    calls.append((text, images, self.context))
                    return json.dumps({'v': self.context['v'], 'a': [['tap_'+str(self.context['v']),
                            'd', 10555.123456789, 10735.123456789]]}), {'wall_seconds': 0}

            args = SimpleNamespace(joint_profile=str(profile), actors=2, cadence=.3, frames=1,
                duration=.9, max_requests=20, clock_offset_ms=10000, seed=2, candidate='test-joint',
                memory=None, run_root=tmp, url='fake', browser_executable=None, chart=None,
                lean=True, compact=False, ack_limit=8)
            summary = await run_episode(args, provider_factory=Provider, env_factory=Env)
            self.assertEqual(summary['requests'], 3)
            self.assertEqual(len(applies), 3)
            for (at, plan), due in zip(applies, [.25, .55, .85]):
                self.assertAlmostEqual(at, due)
                self.assertEqual(plan['taps'][0]['at_ms'], 10555.123456789)
            by_version = {ctx['v']: (text, images, ctx) for text, images, ctx in calls}
            self.assertEqual(by_version[2][2]['f'], [[10100., 10100.]])
            self.assertEqual(by_version[2][2]['now'], 10300.)
            self.assertAlmostEqual(float(by_version[2][1][0]), .1)
            self.assertEqual(by_version[2][2]['rtt'], [100.])
            self.assertTrue(all('PRIVATE_SENTINEL' not in text for text, _, _ in calls))
            self.assertTrue(all('joint_condition' not in text for text, _, _ in calls))
            self.assertTrue((Path(summary['output'])/'final_snapshot.json').exists())

    async def test_capacity_drop_and_end_never_expose_pending_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'profile.json'
            path.write_text(json.dumps({'rows':[{'status':'completed','api_rtt_s':2,
                                               'frame_age_s':0,'transport_overhead_s':0}]}))
            class Provider:
                async def start(self): return self
                async def close(self): pass
                async def act(self,*a): raise AssertionError('pending answer must not be awaited')
            class Env:
                def __init__(self,*a,**kw):self.t=0
                async def __aenter__(self):return self
                async def __aexit__(self,*a):pass
                async def start(self):pass
                async def advance(self,t):self.t=t
                async def capture(self):return {'png':b'x','capture_start_ms':10000+self.t*1000,'capture_end_ms':10000+self.t*1000}
                async def snapshot(self):return {'clock_ms':10000+self.t*1000,'version':0}
                async def apply(self,*a):raise AssertionError('cannot apply undelivered answer')
                async def trusted_evaluator(self):return {'state':'result','judged':52,'total_notes':52,'counts':{'miss':0,'perfect':52}}
            args=SimpleNamespace(joint_profile=str(path),actors=1,cadence=.1,frames=1,duration=.3,
                max_requests=10,clock_offset_ms=10000,seed=1,candidate='capacity',memory=None,
                run_root=tmp,url='fake',browser_executable=None,chart=None,lean=True)
            summary=await run_episode(args,provider_factory=Provider,env_factory=Env)
            self.assertEqual(summary['requests'],1)
            self.assertEqual(summary['dropped_capture_requests'],2)
            self.assertEqual(summary['undelivered_requests_at_end'],1)
            self.assertEqual(summary['delivered_plans'],0)

    def test_joint_rows_validated_without_destroying_correlation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profile.json'
            rows=[{'status':'completed','api_rtt_s':1,'frame_age_s':.2,'transport_overhead_s':.3},
                  {'status':'completed','api_rtt_s':2,'frame_age_s':.4,'transport_overhead_s':.6},
                  {'status':'failed'}]
            path.write_text(json.dumps({'rows':rows}))
            self.assertEqual(load_joint_delays(path)[1],[(1,.2,.3),(2,.4,.6)])
            for bad in [-1,float('nan'),True,None]:
                rows[0]['frame_age_s']=bad;path.write_text(json.dumps({'rows':rows}))
                with self.assertRaises(ValueError):load_joint_delays(path)
