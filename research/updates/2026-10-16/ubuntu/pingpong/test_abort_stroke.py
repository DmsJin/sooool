"""Pure public-state cancellation checks; no simulator/model calls."""
import copy
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"sports/tabletennis"))
from abort_stroke import abort_option,eligible_at_delivery,AbortLifecycle
from candidates import Candidates,menu_prompt


def fixture():
    action={'type':'act','t':.83,'pos':[.73202,-.79328,.20976],
            'normal':[-.15729,.88361,.44102],'vel':[-.10618,1.31018,1.29594]}
    return {'step':1343,'point':5,'ball_state':'coming to you','ball_in_play':True,
            'you_serve':False,'you_receive_serve':True,'serve':{'phase':'done'},'base_xy':[0,-1.55],
            'command':{'phase':'approach','contact_in_s':.63,'pos':[.732,-.7933,.2098],
                       'normal':[-.1573,.8836,.441],'vel':[-.106,1.31,1.296]},
            'recent_applied':[{'step':1323,'point':5,'action':action,
                'execution_feedback':{'table_contact_in_rehearsal':True,
                                      'blade_error_m':.7069,'speed_scale':20}}]}


class AbortTests(unittest.TestCase):
    def test_clear_lifecycle_only_confirmed_and_same_point_old_views(self):
        guard=AbortLifecycle();body={'type':'none','_abortstroke_point':5}
        act={'type':'act'}
        guard.installed(body,5,100,False)
        self.assertFalse(guard.stale_act(act,5,95))
        guard.installed(body,6,100,True)
        self.assertFalse(guard.stale_act(act,5,95))
        guard.installed(body,5,100,True)
        self.assertTrue(guard.stale_act(act,5,95)) # delivery at110 does not freshen obs95
        self.assertTrue(guard.stale_act(act,5,100))
        self.assertFalse(guard.stale_act(act,5,101))
        self.assertFalse(guard.stale_act(act,6,95))
        self.assertFalse(guard.stale_act({'type':'move'},5,95))
        guard.installed(body,5,120,False)
        self.assertEqual(guard.step,100) # refused clear must not extend cutoff

    def test_actual_public_rounding_and_metadata(self):
        s=fixture();o=abort_option(s,4)
        self.assertEqual(o['kind'],'abort_stroke');self.assertEqual(o['action']['type'],'none')
        self.assertEqual(len(o['rehearsal_warning']),2)
        self.assertTrue(eligible_at_delivery(s,o['action']))

    def test_strict_danger_thresholds(self):
        s=fixture();f=s['recent_applied'][0]['execution_feedback'];f['table_contact_in_rehearsal']=False
        for blade,scale,offered in [(.05,20,False),(.1,4,False),(.0501,4.001,True),(.7,float('nan'),False)]:
            f.update(blade_error_m=blade,speed_scale=scale)
            self.assertEqual(abort_option(s,1) is not None,offered)
        f.update(blade_error_m=0,speed_scale=1,table_contact_in_rehearsal=True)
        self.assertIsNotNone(abort_option(s,1))

    def test_stale_or_nonincoming_or_serving_not_offered(self):
        for mutate in [lambda s:s.update(point=6),lambda s:s['command'].update(phase='follow_through'),
                       lambda s:s.update(ball_state='going to the opponent'),lambda s:s.update(ball_in_play=False),
                       lambda s:s['command'].update(contact_in_s=.1),
                       lambda s:s['command'].update(vel=[0,0,0]),
                       lambda s:s['recent_applied'][0].pop('point'),
                       lambda s:s.update(you_serve=True,serve={'phase':'tossed'})]:
            s=fixture();mutate(s);self.assertIsNone(abort_option(s,1))
        s=fixture();s.update(you_serve=True)
        self.assertIsNotNone(abort_option(s,1)) # ordinary rally on our service point

    def test_last_act_only_and_delivery_change(self):
        s=fixture();body=abort_option(s,1)['action']
        newer=copy.deepcopy(s['recent_applied'][0]);newer['step']+=10
        s['recent_applied'].append(newer)
        self.assertIsNone(abort_option(s,1)) # do not search past the newest mismatching act
        self.assertFalse(eligible_at_delivery(s,body))
        s=fixture();s['command']['phase']='follow_through'
        self.assertFalse(eligible_at_delivery(s,body))

    def test_menu_and_prompt_opt_in_default_and_serve_parity(self):
        def build(mode,state):
            with patch('candidates.serve_plan',return_value=None):m=Candidates({'cameras':[]},mode)
            m.player=SimpleNamespace(update=lambda *a:None,predict=lambda:None)
            with patch('candidates.decode',return_value=None):
                return m.build({'state':copy.deepcopy(state),'observation':{'image_png_b64':''}},{})
        s=fixture()
        offered=build('geometry_abortstroke_chunk',s)
        self.assertEqual(offered[-1]['kind'],'abort_stroke')
        self.assertEqual(build('geometry_chunk',s),offered[:-1])
        s['command']['phase']='follow_through'
        baseline=build('geometry_chunk',s)
        self.assertEqual(baseline,build('geometry_abortstroke_chunk',s))
        serving=fixture();serving.update(ball_state='your serve',ball_in_play=False, you_serve=True,serve={'phase':'open'})
        self.assertEqual(build('geometry_chunk',serving),build('geometry_abortstroke_chunk',serving))
        view={'state':serving,'observation':{}}
        self.assertNotIn('Consider the offered abort_stroke',menu_prompt(view,[],{},'geometry_chunk'))
        self.assertIn('Consider the offered abort_stroke',menu_prompt(view,[],{},'geometry_abortstroke_chunk'))

if __name__=='__main__':unittest.main()
