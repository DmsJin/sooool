"""Public-feedback fixtures only; no native world, model or network calls."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from commit_guard import filter_replacements,preserve_at_delivery


class CommitGuardTests(unittest.TestCase):
    def fixture(self):
        action={'type':'act','t':.45,'pos':[0.,-1.4,.2],'normal':[1.,0.,0.]}
        state={'step':110,'point':2,'ball_state':'coming to you','ball_in_play':True,
               'command':{'phase':'approach','contact_in_s':.35,'pos':action['pos'],'normal':action['normal']},
               'recent_applied':[{'step':100,'point':2,'action':action,
                    'execution_feedback':{'blade_error_m':.0004,'normal_error_deg':2.235,'speed_scale':1.443,'table_contact_in_rehearsal':False}}]}
        options=[{'id':0,'kind':'wait'},{'id':1,'kind':'act','contact_step':145,
                  'action':{'type':'act','pos':[.01,-1.4,.2],'normal':[1.,0.,0.]}},
                 {'id':2,'kind':'move','action':{'type':'move','base':[0.,-1.55]}}]
        return state,options

    def test_small_late_change_removed_and_ids_contiguous(self):
        state,options=self.fixture()
        kept=filter_replacements(state,options)
        self.assertEqual([o['kind'] for o in kept],['wait','move'])
        self.assertEqual([o['id'] for o in kept],[0,1])
        self.assertEqual(state['commit_guard']['removed_count'],1)

    def test_bad_mismatched_and_material_changes_kept(self):
        mutations=[lambda s,o:s['recent_applied'][0]['execution_feedback'].update(normal_error_deg=11.568),
                   lambda s,o:s['recent_applied'][0]['execution_feedback'].update(blade_error_m=.02),
                   lambda s,o:s['recent_applied'][0]['execution_feedback'].update(speed_scale=2.1),
                   lambda s,o:s['recent_applied'][0]['execution_feedback'].update(table_contact_in_rehearsal=True),
                   lambda s,o:s['recent_applied'][0].update(point=1),
                   lambda s,o:s['recent_applied'][0]['action'].update(t=.50),
                   lambda s,o:s['recent_applied'][0]['action'].update(pos=[.1,-1.4,.2]),
                   lambda s,o:s['recent_applied'][0]['action'].update(normal=[0.,1.,0.]),
                   lambda s,o:o[1].update(contact_step=150),
                   lambda s,o:o[1]['action'].update(pos=[.02,-1.4,.2]),
                   lambda s,o:o[1]['action'].update(normal=[.99,.1,0.]),
                   lambda s,o:s.update(ball_state='going to the opponent'),
                   lambda s,o:s['command'].update(phase='follow_through')]
        for mutation in mutations:
            state,options=self.fixture();mutation(state,options)
            self.assertEqual(len(filter_replacements(state,options)),3)
            self.assertEqual(state['commit_guard']['removed_count'],0)
        state,options=self.fixture()
        state['step']=90;state['command']['contact_in_s']=.55
        self.assertEqual(len(filter_replacements(state,options)),3)

    def test_latest_matching_bad_feedback_cannot_use_older_good(self):
        state,options=self.fixture()
        bad=copy.deepcopy(state['recent_applied'][0]);bad['execution_feedback']['normal_error_deg']=10
        state['recent_applied'].append(bad)
        self.assertEqual(len(filter_replacements(state,options)),3)

    def test_default_mode_never_calls_guard(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'sports/tabletennis'))
        from candidates import Candidates
        with patch('candidates.serve_plan',return_value=None):menu=Candidates({'cameras':[]},'geometry_chunk')
        view={'state':{'step':1,'point':1,'base_xy':[0.,-1.55],'base_rest':[0.,-1.55],
                       'ball_state':'dead','ball_in_play':False},'observation':{}}
        with patch('commit_guard.filter_replacements',side_effect=AssertionError('must remain optional')):
            menu.build(view,{})
        self.assertNotIn('commit_guard',view['state'])

    def test_inflight_choice_rechecked_after_first_good_plan_applies(self):
        # A later GPT choice was prepared at 1821, before the first plan took
        # effect at 1828; delivery happens only after its planner stall at 1840.
        first_normal=[.1672,.8456,.5069]
        replacement={'type':'act','t':.52,'pos':[.01,-1.4,.2],'normal':[.1409,.7525,.6433]}
        old={'step':1821,'point':2,'ball_state':'coming to you','ball_in_play':True,'command':'none','recent_applied':[]}
        self.assertFalse(preserve_at_delivery(old,replacement,1873,normal_limit=15))
        fresh,_=self.fixture()
        fresh['step']=1840
        fresh['command'].update(contact_in_s=.33,normal=first_normal)
        fresh['recent_applied'][0].update(step=1828)
        fresh['recent_applied'][0]['action'].update(t=.45,normal=first_normal)
        self.assertFalse(preserve_at_delivery(copy.deepcopy(fresh),replacement,1873,normal_limit=2))
        self.assertTrue(preserve_at_delivery(fresh,replacement,1873,normal_limit=15))
        fresh['recent_applied'] += [{'step':1830+i,'point':2,'action':{'type':'move'}} for i in range(5)]
        self.assertTrue(preserve_at_delivery(fresh,replacement,1873,normal_limit=15))
        self.assertEqual(fresh['commit_guard']['normal_shift_limit_deg'],15)
        self.assertFalse(preserve_at_delivery(copy.deepcopy(fresh),replacement,1876,normal_limit=15))
        self.assertFalse(preserve_at_delivery(copy.deepcopy(fresh),{**replacement,'pos':[.02,-1.4,.2]},1873,normal_limit=15))
        self.assertFalse(preserve_at_delivery(copy.deepcopy(fresh),{**replacement,'normal':[0.,1.,0.]},1873,normal_limit=15))


if __name__=='__main__':unittest.main()
