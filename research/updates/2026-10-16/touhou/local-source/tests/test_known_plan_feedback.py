import hashlib
import json
import tempfile
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch
from research.known_plan_feedback import captured_control_context, observation_gate_open, validate_known_plan_feedback
from research.policies import make_prompt
from research.run_episode import run
from research.scheduler import VirtualScheduler
from research.wire_schema import decision_schema

CANDIDATE='tracking_dodge_safe_intercept_v2'
PROFILE={'kind':'modeled_independent_k1_pipeline_from_historical_serial_terminal','p50_s':2.3916291749919765,'p95_s':3.1920291490096133}
CONFIG={'decision_fanout':1,'capacity':4,'wait_for_winner':True,'wait_for_move':False,'rolling_observations':False,'known_plan_feedback':True,'chunk_size':4,'max_duration':48,'structured':True}
GOLDEN=[({'chunk_size': 1, 'max_duration': 48, 'structured': True, 'wait_for_move': True, 'wait_for_winner': True}, 'fda5fc3566c968f32abc380c08c68564d7fdbcfa8f451de30fb2ba29a55a3ab5'), ({'chunk_size': 4, 'max_duration': 48, 'structured': True, 'wait_for_move': False, 'wait_for_winner': True}, '3ee03b9d829782dfebce952fd717f5ed8197088c11388d5f731f4fa95855d348'), ({'chunk_size': 1, 'max_duration': 48, 'structured': True, 'wait_for_move': False, 'wait_for_winner': False, 'rolling_observations': True, 'decision_fanout': 1, 'capacity': 4}, 'ecc79c56b3baff2839c3f49266d6ec3708db0d164012d999f5c5ac60c3225af4')]

def observation():
    return {'image_frames':[10,40,70],'held':[3,1,1,0],
        'clock':{'frame':70,'visual_frame':235,'held':[3,1,1,0],'remaining':20,
                 'active_plan':{'action':[3,1,1,0],'start':60,'end':90},
                 'pending_plan':[[7,1,1,0,8],[0,1,1,0,48],[3,1,0,0,12]],
                 'private_entity_state':'MUST_NOT_APPEAR'}}

class KnownPlanFeedbackTests(unittest.TestCase):
    def test_complete_atomic_queue_overrides_old_loop_argument(self):
        ob=observation();wrong={'action':[7,0,0,1],'start':1,'end':2}
        text=make_prompt(CANDIDATE,ob,CONFIG,PROFILE,wrong)
        self.assertIn('Known returned plan: '+json.dumps(ob['clock']['active_plan'],separators=(',',':')),text)
        self.assertNotIn(json.dumps(wrong,separators=(',',':')),text)
        line=next(x for x in text.splitlines() if x.startswith('Captured control schedule'))
        context=json.loads(line.split(': ',1)[1][:-1])
        self.assertEqual(set(context),{'frame','visual_frame','held','remaining','active_plan','pending_plan'})
        self.assertEqual(context['pending_plan'],ob['clock']['pending_plan'])
        self.assertNotIn('MUST_NOT_APPEAR',text)
        self.assertIn('no other unknown model answer can change your controls',text)
        self.assertIn('Death, respawn, boundaries and cinematic freezes',text)
        self.assertIn('Modeled per-request delay',text)
        self.assertNotIn('Pending answers are unknown',text)
        self.assertEqual(decision_schema(CANDIDATE,4,48)['properties']['plan']['maxItems'],4)

    def test_missing_or_inconsistent_context_fails_closed(self):
        for field in ('frame','visual_frame','held','remaining','active_plan','pending_plan'):
            ob=observation();del ob['clock'][field]
            with self.assertRaises(ValueError):make_prompt(CANDIDATE,ob,CONFIG,PROFILE)
        ob=observation();ob['clock']['active_plan']['end']=999
        with self.assertRaises(ValueError):captured_control_context(ob)
        ob=observation();ob['clock']['pending_plan']=None
        with self.assertRaises(ValueError):captured_control_context(ob)
        ob=observation();ob['clock'].update(remaining=0,active_plan=None,pending_plan=[])
        self.assertEqual(captured_control_context(ob)['pending_plan'],[])

    def test_two_and_four_chunk_suffix_is_reported_without_invention(self):
        for count in (2,4):
            ob=observation();ob['clock']['pending_plan']=ob['clock']['pending_plan'][:count-1]
            text=make_prompt(CANDIDATE,ob,{**CONFIG,'chunk_size':count},PROFILE)
            line=next(x for x in text.splitlines() if x.startswith('Captured control schedule'))
            context=json.loads(line.split(': ',1)[1][:-1])
            self.assertEqual(context['pending_plan'],ob['clock']['pending_plan'])
            self.assertEqual(len(context['pending_plan']),count-1)

    def test_invalid_config_before_external_work(self):
        for change in ({'decision_fanout':4},{'decision_fanout':True},{'wait_for_winner':False},
                       {'wait_for_move':True},{'rolling_observations':True},{'known_plan_feedback':1}):
            config={**CONFIG,**change}
            with self.assertRaises(ValueError):validate_known_plan_feedback(config)
            with tempfile.TemporaryDirectory() as tmp, patch('research.run_episode.BrowserEnv') as browser:
                target=Path(tmp)/'out'
                with self.assertRaises(ValueError):run(config,target)
                browser.assert_not_called();self.assertFalse(target.exists())

    def test_default_bytes_equal_frozen_base(self):
        self.assertEqual(len(GOLDEN),3)
        ob={'image_frames':[10,40,70],'held':[3,1,1,0]};known={'action':[3,1,1,0],'start':60,'end':90}
        for config,expected in GOLDEN:
            for extra in ({},{'known_plan_feedback':False}):
                text=make_prompt(CANDIDATE,ob,{**config,**extra},PROFILE,known)
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(),expected)

    def test_runner_gate_allows_known_move_not_two_unknown_answers(self):
        def answer(plan):
            f=Future();f.set_result({'plan':plan});return f
        scheduler=VirtualScheduler(capacity=4)
        scheduler.submit(0,answer([[3,1,1,0,48]]),10)
        scheduler.advance(10);self.assertEqual(scheduler.action_at(10),[3,1,1,0])
        scheduler.advance(16);clock={'held':[3,1,1,0],'pending_plan':[]}
        def gate(lastissued,config=CONFIG):
            return observation_gate_open(config,clock,scheduler.available(),lastissued,scheduler.latest_observation,scheduler.has_pending_observation)
        self.assertTrue(gate(0));self.assertFalse(gate(0,{**CONFIG,'wait_for_move':True}))
        scheduler.submit(16,answer([[0,1,1,0,1]]),40)
        self.assertFalse(gate(16));self.assertEqual(scheduler.advance(30),[])
        self.assertEqual(scheduler.action_at(30),[3,1,1,0]);self.assertFalse(gate(16))
        self.assertEqual([e['disposition'] for e in scheduler.advance(56)],['applied'])
        self.assertEqual(scheduler.action_at(56),[0,1,1,0]);self.assertTrue(gate(16));self.assertEqual(scheduler.inflight,0)

    def test_invalid_completed_request_unblocks_without_applying_unknown_plan(self):
        scheduler=VirtualScheduler(capacity=4);bad=Future();bad.set_result({'plan':[]})
        scheduler.submit(0,bad,10)
        clock={'held':[0,1,1,0],'pending_plan':[]}
        def gate():
            return observation_gate_open(CONFIG,clock,True,0,scheduler.latest_observation,scheduler.has_pending_observation)
        self.assertFalse(gate())
        events=scheduler.advance(10)
        self.assertEqual([e['disposition'] for e in events],['invalid'])
        self.assertEqual(scheduler.latest_observation,-1)
        self.assertTrue(gate())

if __name__=='__main__':unittest.main()
