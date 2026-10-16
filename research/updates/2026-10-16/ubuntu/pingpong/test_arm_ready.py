"""Offline public gating and native action-schema checks; no world or model calls."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sports/tabletennis'))
from candidates import Candidates
from arm_ready import eligible,preparation
from policy import parse


class ArmReadyTests(unittest.TestCase):
    def state(self):
        return {'step':100,'point':7,'base_xy':[0.,-1.67],'base_rest':[0.,-1.67],
                'command':'none (the arm returns to / holds the ready pose)',
                'ball_state':'going to the opponent','ball_in_play':True}

    def menu(self,mode='geometry_midbase_armready_chunk'):
        with patch('candidates.serve_plan',return_value=None):return Candidates({'cameras':[]},mode)

    def test_outgoing_ready_only_and_absolute_timing(self):
        state=self.state();menu=self.menu()
        options=menu.build({'state':state,'observation':{}},{})
        prep=next(o for o in options if o.get('purpose')=='armready')
        self.assertEqual(prep['contact_step'],160)
        self.assertEqual(prep['action']['t'],.6)
        self.assertEqual(prep['action']['vel'],[0.,0.,0.])
        self.assertAlmostEqual(np.linalg.norm(prep['action']['normal']),1.)
        self.assertFalse(prep['armready']['ball_path_clearance_guaranteed'])
        self.assertIn('not a return',prep['description'])
        for changed in ({'ball_state':'coming to you'},{'ball_state':'your serve'},
                        {'ball_in_play':False},{'command':{'phase':'approach'}},
                        {'command':{'phase':'follow_through'}}):
            other={**state,**changed};self.assertFalse(eligible(other,[]))
        self.assertTrue(eligible({**state,'command':{'phase':'ready'}},[]))

    def test_once_per_point_and_delivery_revalidation(self):
        state=self.state();menu=self.menu();prep=preparation(state)
        record={'action':prep['action'],'step':110}
        state['recent_applied']=[record]
        self.assertFalse(any(o.get('purpose')=='armready' for o in menu.build({'state':state,'observation':{}},{})))
        state['recent_applied']=[]
        self.assertFalse(any(o.get('purpose')=='armready' for o in menu.build({'state':state,'observation':{}},{})))
        self.assertFalse(eligible({**state,'ball_state':'coming to you'},[]))
        self.assertFalse(eligible(state,[record]))
        self.assertTrue(eligible({**state,'point':8},[record]))

    def test_default_and_service_offers_unchanged(self):
        state=self.state()
        self.assertFalse(any(o.get('purpose')=='armready' for o in self.menu('geometry_midbase_chunk').build({'state':state,'observation':{}},{})))
        state.update(ball_state='your serve',ball_in_play=False,you_serve=True,serve={'phase':'open'})
        self.assertFalse(any(o.get('purpose')=='armready' for o in self.menu().build({'state':state,'observation':{}},{})))

    def test_action_parses_under_real_high_schema(self):
        body=preparation(self.state())['action']
        self.assertEqual(parse(json.dumps(body)),body)
        # action_high imports only these public constants; no native model needed.
        constants=SimpleNamespace(BASE_HI=np.array([1.,-1.5]),BASE_LO=np.array([-1.,-2.4]),CONTROL_DT=.01)
        spec=importlib.util.spec_from_file_location('offline_action_high',ROOT/'sports/tabletennis/sim/action_high.py')
        module=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'rcb_tt':constants}):spec.loader.exec_module(module)
        native=module.validate(body,None)
        self.assertIsInstance(native,dict)
        self.assertEqual(native['type'],'act')
        self.assertEqual(native['base'],[0.,-1.67])
        self.assertNotIn('_armready_point',native)
        # The ordinary act executor converts observation-relative contact to delivery time.
        self.assertAlmostEqual((160-120)*.01,.4)


if __name__=='__main__':unittest.main()
