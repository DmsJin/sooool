"""Offline controller tests: early action readiness is not terminal accounting."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from research.run_episode import DecisionPool, run
from research.recover_prefix import durable_write


class EarlyDeliveryTests(unittest.TestCase):
    def episode(self, *, fanout=2, capacity=8, stride=1, end=8, terminal_at=None, fail=False, defer_old=False, max_calls=None):
        class Pool:
            instance = None
            def __init__(self, config, out, key):
                Pool.instance=self;self.calls=[];self.buffer={};self.closed=False
            def submit(self, prompt, images, directory):
                index=len(self.calls);future=Future()
                # Later list order is actually ready first in each cohort.
                early={'answer': '[3,1,1,0,12]', 'plan': [[3,1,1,0,12]],
                       'meta': {'request_id': str(index), 'early_legal': True,
                                'terminal_pending': True, 'early_legal_ready_ns': 200-index}}
                durable_write(directory/'early_result.json',early)
                if not defer_old or index>=2:self.buffer[str(directory)]=early
                self.calls.append((future,directory,early))
                return future
            def take_early(self,directory):return self.buffer.pop(str(directory),None)
            def settle(self):
                for index,(future,directory,early) in enumerate(self.calls):
                    if future.done():continue
                    if fail and index==0:future.set_exception(RuntimeError('terminal tier mismatch'))
                    else:
                        result={**early,'meta': {'request_id':str(index),'usd':'0.1'},'race_completed_ns':500+index}
                        durable_write(directory/'result.json',result);future.set_result(result)
            def close(self):self.closed=True;self.settle()
        class Env:
            instance=None
            def __init__(self,*args,**kwargs):self.frame=-1;self.applies=[];Env.instance=self
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def reset(self,*args,**kwargs):pass
            def clock(self):
                return {'frame':self.frame,'visual_frame':self.frame,'intro':0,'held':[0,1,1,0],
                        'status':'won' if self.frame>=end else 'playing'}
            def diagnostics(self):
                self.frame+=1
                if defer_old and self.frame==2:
                    for _,directory,early in Pool.instance.calls[:2]:Pool.instance.buffer[str(directory)]=early
                if terminal_at is not None and self.frame>=terminal_at:Pool.instance.settle()
                return {'clock':self.clock(),'state':{'status':self.clock()['status'],'tick':self.frame,
                        'hits':0,'score':0,'boss':{'hp':0},'player':{'lives':1,'bombs':1}}}
            def capture(self):return {'frame':self.frame,'clock':self.clock(),'held':[0,1,1,0],'png':b'png'}
            def apply(self,plan):
                self.applies.append({'frame':self.frame,'pending':sum(not f.done() for f,_,_ in Pool.instance.calls)})
                return self.clock()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);profile=root/'profile.json';profile.write_text('{"samples_s":[1]}');out=root/'episode'
            config={'profile':str(profile),'url':'unused','seed':1,'candidate':'unused','provider':'api',
                    'mode':'realtime','structured':True,'early_action_delivery':True,'workers':capacity,
                    'capacity':capacity,'decision_fanout':fanout,'decision_stride':stride,'image_stride':1}
            if max_calls is not None:config['max_calls']=max_calls
            with patch('research.run_episode.BrowserEnv',Env),patch('research.run_episode.DecisionPool',Pool),patch('research.run_episode.make_prompt',return_value='prompt'),patch('research.run_episode.time.sleep'):
                if fail:
                    with self.assertRaisesRegex(RuntimeError,'Terminal decision validation failed'):run(config,out)
                else:run(config,out)
            read=lambda name:json.loads((out/name).read_text())
            rows=[json.loads(x) for x in (out/'decisions.jsonl').read_text().splitlines()]
            actions=[json.loads(x) for x in (out/'actions.jsonl').read_text().splitlines()]
            return read('summary.json'),rows,actions,Env.instance.applies,Pool.instance

    def test_call_cap_never_admits_a_partial_race(self):
        summary,rows,actions,applies,pool=self.episode(max_calls=3)
        self.assertEqual(len(rows),2)
        self.assertEqual(summary['calls'],2)
        self.assertEqual(len(actions),1)

    def test_early_apply_precedes_terminal_and_pending_requests_hold_capacity_eight(self):
        summary,rows,actions,applies,pool=self.episode()
        self.assertEqual(len(rows),8)
        self.assertEqual([x['seq'] for x in actions],[1,3,5,7])
        self.assertEqual([x['observed_frame'] for x in actions],[0,1,2,3])
        self.assertGreater(applies[0]['pending'],0)
        self.assertEqual(sum(x['disposition']=='applied' for x in rows),4)
        self.assertTrue(summary['terminal_accounting_complete'])
        self.assertTrue(pool.closed)
        self.assertTrue(all(f.done() for f,_,_ in pool.calls))
        self.assertAlmostEqual(sum(float(x['meta']['usd']) for x in rows),.8)
        self.assertTrue(all('usd' not in x['early_result']['meta'] for x in rows))
        self.assertTrue(all(x['capture_to_apply_s']>=0 for x in actions))

    def test_newer_observation_overrides_simultaneously_ready_older_cohort(self):
        summary,rows,actions,applies,pool=self.episode(defer_old=True)
        self.assertEqual(actions[0]['seq'],3)
        self.assertEqual(actions[0]['observed_frame'],1)
        self.assertTrue(all(row['disposition']=='superseded' for row in rows[:2]))

    def test_terminal_failure_stops_admission_during_play(self):
        summary,rows,actions,applies,pool=self.episode(terminal_at=2,fail=True)
        self.assertEqual(len(rows),4)
        self.assertFalse(summary['won'])
        self.assertTrue(summary['validation_failure'])

    def test_terminal_completion_does_not_apply_same_observation_twice(self):
        summary,rows,actions,applies,pool=self.episode(stride=20,terminal_at=4)
        self.assertEqual(len(actions),1)
        self.assertEqual(actions[0]['seq'],1)
        self.assertEqual(len(rows),2)
        self.assertTrue(summary['won'])

    def test_terminal_failure_after_engine_win_invalidates_episode_and_drains_all(self):
        summary,rows,actions,applies,pool=self.episode(fail=True)
        self.assertEqual(summary['status'],'won')
        self.assertFalse(summary['won'])
        self.assertFalse(summary['complete'])
        self.assertTrue(summary['validation_failure'])
        self.assertTrue(all(f.done() for f,_,_ in pool.calls))
        self.assertEqual(len(rows),8)
        self.assertEqual(sum('error' in x for x in rows),1)
        self.assertAlmostEqual(sum(float(x.get('meta',{}).get('usd',0)) for x in rows),.7)

    def test_pool_publishes_only_after_durable_write_and_preserves_ready_clock(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);pool=DecisionPool({},directory)
            result={'answer':'[3,1,1,0,12]','meta':{'early_legal_ready_ns':123}}
            try:
                def check_write(path,payload):
                    self.assertIsNone(pool.take_early(directory));durable_write(path,payload)
                with patch('research.run_episode.write',side_effect=check_write):pool.publish_early(directory,result)
                delivered=pool.take_early(directory)
                self.assertEqual(delivered['meta']['early_legal_ready_ns'],123)
                self.assertEqual(delivered['plan'],[[3,1,1,0,12]])
                self.assertIsNone(pool.take_early(directory))
                self.assertTrue((directory/'early_result.json').exists())
            finally:pool.close()

    def test_real_pool_future_remains_pending_after_fake_stream_callback(self):
        published=threading.Event();terminal=threading.Event()
        class Client:
            def decide(self,prompt,images,validate=None,timing_origin=None,on_legal_action=None):
                on_legal_action({'answer':'[3,1,1,0,12]',
                                 'meta':{'early_legal_ready_ns':123,'early_legal':True,'terminal_pending':True}})
                published.set()
                if not terminal.wait(5):raise TimeoutError('test terminal was not released')
                return {'answer':'[3,1,1,0,12]','meta':{'usd':'0.1'}}
            def close(self):pass
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);pool=DecisionPool({'provider':'api','early_action_delivery':True},directory)
            def worker():
                pool.local.client=Client()
                return pool.decide('prompt',[],directory)
            try:
                future=pool.pool.submit(worker)
                self.assertTrue(published.wait(5))
                self.assertFalse(future.done())
                early=pool.take_early(directory)
                self.assertEqual(early['plan'],[[3,1,1,0,12]])
                self.assertTrue((directory/'early_result.json').exists())
                self.assertFalse((directory/'result.json').exists())
                terminal.set()
                result=future.result(timeout=5)
                self.assertEqual(result['meta']['usd'],'0.1')
                self.assertTrue((directory/'result.json').exists())
            finally:terminal.set();pool.close()

    def test_opt_in_rejects_simulation_native_or_unstructured_before_output(self):
        for config in ({'mode':'sim','provider':'api','structured':True},
                       {'mode':'realtime','provider':'subscription','structured':True},
                       {'mode':'realtime','provider':'api'}):
            with self.assertRaisesRegex(ValueError,'realtime structured API'):
                run({'early_action_delivery':True,**config},'unused')


if __name__=='__main__':unittest.main()
