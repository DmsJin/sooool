import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'environments/asterix'))
import runner

class FakeEnv:
    def step(self,action):return np.zeros((210,160,3),dtype=np.uint8),0,False,False,{'lives':3}
    def close(self):pass

def fake_env(seed):return FakeEnv(),np.zeros((210,160,3),dtype=np.uint8),{'lives':3},0

class RunnerTests(unittest.TestCase):
    def test_partial_episode_is_retained_in_run_aggregate(self):
        recipe=json.loads((ROOT/'recipes/asterix.json').read_text())
        class Client:
            def close(self):pass
        def fail(recipe,out,*args):
            out.mkdir()
            (out/'summary.json').write_text('{"status":"interrupted","score":50}')
            raise RuntimeError('provider timeout')
        with tempfile.TemporaryDirectory() as d,patch.object(runner,'run_episode',side_effect=fail):
            out=Path(d)
            with self.assertRaises(RuntimeError):
                runner.run_recipe(ROOT,recipe,out,SimpleNamespace(seed=5,duration=20),lambda **kw:Client())
            self.assertEqual(json.loads((out/'summary.json').read_text())['episodes'][0]['score'],50)

    def test_saved_outputs_reproduce_selected_whole_trajectory(self):
        recipe=json.loads((ROOT/'recipes/asterix.json').read_text())
        task,delays=runner.build_task(ROOT,recipe,'simulation')
        reference=ROOT/'artifacts/asterix/serial-selected/english_reason/seed-5'
        decisions=[json.loads(x) for x in (reference/'decisions.jsonl').read_text().splitlines()]
        class Saved:
            count=0
            def act(self,prompt,images,directory):
                r=decisions[self.count];self.count+=1
                assert [hashlib.sha256(x).hexdigest() for x in images]==r['image_sha256']
                return r['answer'],r['meta']
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'episode';client=Saved()
            summary=runner.run_episode(recipe,out,5,1200,task,delays,client,'simulation')
            self.assertEqual((summary['score'],summary['lives'],client.count),(500,2,44))
            self.assertEqual((out/'steps.jsonl').read_bytes(),(reference/'steps.jsonl').read_bytes())
            self.assertEqual(json.loads((out/'actions.json').read_text()),json.loads((reference/'actions.json').read_text()))

    def test_real_clock_advances_while_reply_pending(self):
        recipe=json.loads((ROOT/'recipes/asterix-action-only.json').read_text())
        class Clock:
            now=0.
            def monotonic(self):return self.now
            def sleep(self,seconds):self.now+=seconds
        clock=Clock()
        class Delayed:
            def __init__(self):self.due=clock.now+.5
            def done(self):return clock.now>=self.due
            def result(self):return {'answer':'1','chosen':1,'reason':None,'meta':{}}
        class Pool:
            def __init__(self,**kwargs):pass
            def submit(self,*args):return Delayed()
            def shutdown(self,**kwargs):pass
        with tempfile.TemporaryDirectory() as d,patch.object(runner,'ThreadPoolExecutor',Pool),patch.object(runner,'time',clock):
            out=Path(d)/'episode'
            result=runner.run_episode(recipe,out,5,12,'task',[.5],object(),'realtime',env_factory=fake_env)
            steps=[json.loads(x) for x in (out/'steps.jsonl').read_text().splitlines()]
            self.assertEqual([x['action'] for x in steps],[0]*6+[1]*6)
            self.assertAlmostEqual(result['environment_wall_seconds'],1.)
            self.assertEqual(result['frames'],12)
            issued=[json.loads(x) for x in (out/'issued.jsonl').read_text().splitlines()]
            self.assertTrue(all(x['sampled_capture_to_complete_s'] is None for x in issued))

    def test_invalid_reply_retains_interrupted_episode(self):
        recipe=json.loads((ROOT/'recipes/asterix-action-only.json').read_text())
        class Invalid:
            def act(self,*args):return 'UP',{}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'episode'
            with self.assertRaises(RuntimeError):
                runner.run_episode(recipe,out,5,12,'task',[.1],Invalid(),'simulation',env_factory=fake_env)
            self.assertEqual(json.loads((out/'summary.json').read_text())['status'],'interrupted')
            self.assertIn('error_type',(out/'decisions.jsonl').read_text())

    def test_api_early_action_applies_once_but_request_slot_waits_for_terminal(self):
        recipe=json.loads((ROOT/'recipes/asterix.json').read_text())
        class Clock:
            now=0.
            def monotonic(self):return self.now
            def sleep(self,seconds):self.now+=seconds
        clock=Clock()
        class Client:
            provider='openai_api'
            published=False
            def poll_action(self):
                if clock.now>=.25 and not self.published:
                    self.published=True
                    return {'directory':'call-00000','chosen':2,'reason':'Chase food.'}
        class Delayed:
            def done(self):return clock.now>=.75
            def result(self):return {'answer':'{"action":2,"reason":"Chase food."}','chosen':2,'reason':'Chase food.','meta':{}}
        class Pool:
            def __init__(self,**kwargs):self.calls=0
            def submit(self,*args):
                self.calls+=1
                return Delayed()
            def shutdown(self,**kwargs):pass
        with tempfile.TemporaryDirectory() as d,patch.object(runner,'ThreadPoolExecutor',Pool),patch.object(runner,'time',clock):
            out=Path(d)/'episode'
            summary=runner.run_episode(recipe,out,5,12,'task',[.5],Client(),'realtime',env_factory=fake_env)
            steps=[json.loads(x) for x in (out/'steps.jsonl').read_text().splitlines()]
            self.assertEqual([s['action'] for s in steps],[0]*3+[2]*9)
            self.assertEqual(summary['calls'],1)
            self.assertEqual(summary['paid_api_calls'],1)
            self.assertEqual(summary['new_subscription_calls'],0)
            actions=json.loads((out/'actions.json').read_text())
            self.assertEqual(len(actions),1)
            self.assertEqual(actions[0]['frame'],3)
            self.assertTrue(json.loads((out/'deliveries.json').read_text())[0]['terminal_pending'])

    def test_schema_keeps_english_punctuation_and_rejects_bad_action(self):
        self.assertEqual(runner.parse_decision('{"action":2,"reason":"Food is in the player’s row."}','action_reason')[0],2)
        with self.assertRaises(ValueError):runner.parse_decision('{"action":true,"reason":"Move."}','action_reason')

if __name__=='__main__':unittest.main()
