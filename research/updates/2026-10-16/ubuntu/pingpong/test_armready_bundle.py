"""Offline chunk admission and schema checks; no game or model calls."""
import copy
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'sports/tabletennis'))
from arm_ready import preparation,bundle_first,bundle_followups,installed_prep_step,prep_reply_installed
from candidates import Candidates,menu_prompt
import test_arm_ready as prior_checks


class BundleTests(unittest.TestCase):
    def test_opt_in_bundle_keeps_old_armready_schema(self):
        state=prior_checks.ArmReadyTests().state()
        self.assertEqual(preparation(state)['kind'],'act')
        option=preparation(state,bundle=True)
        self.assertEqual(option['kind'],'armready_bundle')
        body=bundle_first(option,120)
        self.assertAlmostEqual(body['t'],.4)
        self.assertIsNone(bundle_first(option,158))
        self.assertEqual(option['actions'][1]['action']['base'],[0.,-1.67])
        self.assertEqual(option['actions'][1]['after_steps'],0)

    def test_only_installed_same_point_prep_enqueues_move(self):
        option=preparation(prior_checks.ArmReadyTests().state(),bundle=True)
        success=installed_prep_step({'type':'traj'},{'command':'traj'},120)
        queued=bundle_followups(option,success,7,2,100)
        self.assertEqual(len(queued),1)
        self.assertEqual((queued[0]['due'],queued[0]['point'],queued[0]['action']['type']),(120,7,'move'))
        for low,result in [({'type':'noop'},{}),({'type':'traj'},{'rejected':'discontinuous'}),({'type':'traj'},{})]:
            effect=installed_prep_step(low,result,120)
            self.assertEqual(bundle_followups(option,effect,7,2,100),[])
        self.assertEqual(bundle_followups(option,success,8,2,100),[])

    def test_realtime_requires_public_installed_command(self):
        option=preparation(prior_checks.ArmReadyTests().state(),bundle=True);body=bundle_first(option,120)
        reply={'took_effect':{'step':120,'stroke':{'n_swing_steps':40}},
               'now':{'step':125,'point':7,'command':{'phase':'approach','pos':body['pos'],
                        'normal':body['normal'],'contact_in_s':.35}}}
        self.assertTrue(prep_reply_installed(reply,body))
        for change in ({'http_status':409},{'now':{'point':8,'command':reply['now']['command']}},
                       {'now':{'point':7,'command':'none'}},{'took_effect':{'step':120,'stroke':{}}}):
            self.assertFalse(prep_reply_installed({**reply,**change},body))

    def test_candidate_and_guidance_only_change_with_modifier(self):
        state=prior_checks.ArmReadyTests().state();view={'state':state,'observation':{}}
        for mode,kind in [('geometry_armready_chunk','act'),('geometry_armready_prepbase_chunk','armready_bundle')]:
            with patch('candidates.serve_plan',return_value=None):menu=Candidates({'cameras':[]},mode)
            opts=menu.build(copy.deepcopy(view),{})
            self.assertEqual(next(o['kind'] for o in opts if o.get('purpose')=='armready'),kind)
            prompt=menu_prompt(view,opts,{},mode)
            self.assertEqual('then sets receive base_rest' in prompt,'_prepbase_' in mode)

    def test_both_chunk_actions_use_native_high_schema(self):
        # Reuse the real action_high validator check, with the same constant-only
        # loading strategy as the existing offline test.
        import importlib.util,numpy as np
        from types import SimpleNamespace
        root=Path(__file__).resolve().parents[2]
        spec=importlib.util.spec_from_file_location('bundle_native_schema',root/'sports/tabletennis/sim/action_high.py')
        module=importlib.util.module_from_spec(spec)
        constants=SimpleNamespace(BASE_HI=np.array([1.,-1.5]),BASE_LO=np.array([-1.,-2.4]),CONTROL_DT=.01)
        with patch.dict(sys.modules,{'rcb_tt':constants}):spec.loader.exec_module(module)
        option=preparation(prior_checks.ArmReadyTests().state(),bundle=True)
        for item in option['actions']:
            validated=module.validate(item['action'],None)
            self.assertIsInstance(validated,dict)
            self.assertEqual(validated['type'],item['action']['type'])


if __name__=='__main__':unittest.main()
