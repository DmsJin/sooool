"""Versioned admission prevents concurrent old deltas from moving a newer plan."""
import copy
import json
from pathlib import Path
import sys
import time
import unittest
try:
    import mujoco  # noqa: F401
except ImportError:  # root env; PCBA uses environments/pcba/requirements.txt
    raise unittest.SkipTest('PCBA tests need the isolated PCBA environment')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environments/pcba'))
from pcba_gym.pipeline import parse_pipeline, rejection


def packet():
    return {'sequence':4,'parent_revision':2,'requires_parent_success':True,'capture_wall':10.,'capture_time_s':8.,
            'expected_start_pose_m_rad':[0.,-.08,1.025,0.],
            'decision':{'start_guard':{'vacuum_ok':True,'fixture_board_present':None,
                'clamp_state':'open','tester_state':None,'result_test_id':'T-0001'}}}


def observation():
    return {'capture_time_s':10.,'robot':{'commanded_tcp_pose_m_rad':[0.,-.08,1.025,0.],'vacuum_ok':True},
            'fixture':{'board_present':False,'clamp_state':'open','tester_state':'complete','result':{'test_id':'T-0001'}}}


class PipelineTests(unittest.TestCase):
    def reject(self,p=None,o=None,**kw):
        args={'revision':2,'parent_success':True,'latest_selected':3,'observation':o or observation(),'wall_now':12.,'ttl':12.}
        args.update(kw);return rejection(p or packet(),**args)

    def test_exact_successful_parent_and_public_guards_admit(self):
        self.assertIsNone(self.reject())

    def test_older_reply_cannot_overwrite_newer_plan(self):
        self.assertEqual(self.reject(revision=3),'superseded_parent')
        self.assertEqual(self.reject(latest_selected=5),'superseded_sequence')

    def test_failed_or_partially_executed_parent_invalidates_speculation(self):
        self.assertEqual(self.reject(parent_success=False),'parent_failed')
        o=observation();o['robot']['commanded_tcp_pose_m_rad'][0]=.001
        self.assertEqual(self.reject(o=o),'incompatible_robot_start')

    def test_wall_and_sim_expiry_are_independent(self):
        self.assertEqual(self.reject(wall_now=23.),'expired_source')
        o=observation();o['capture_time_s']=21.
        self.assertEqual(self.reject(o=o),'expired_source')

    def test_grasp_clamp_and_result_id_feedback_gate_next_motion(self):
        for key,value in (('vacuum_ok',False),('clamp_state','closed'),('result_test_id','T-0002')):
            o=observation()
            if key=='vacuum_ok':o['robot'][key]=value
            elif key=='result_test_id':o['fixture']['result']['test_id']=value
            else:o['fixture'][key]=value
            self.assertEqual(self.reject(o=o),'start_guard_mismatch')

    def test_pipeline_parser_preserves_literal_actions_and_rejects_bad_guards(self):
        d={'summary':'Continue from committed endpoint.','memory':'Awaiting grip feedback.','done':False,
            'start_guard':packet()['decision']['start_guard'],
            'segments':[{'delta_xyz_m':[.001,0,0],'delta_yaw_rad':0.,'repeat':2,'vacuum':None,'fixture':None}]}
        parsed,actions=parse_pipeline(json.dumps(d));self.assertEqual(len(actions),2)
        self.assertEqual(actions[0]['delta_xyz_m'],[.001,0,0]);self.assertTrue(parsed['start_guard']['vacuum_ok'])
        d['start_guard']['vacuum_ok']=1
        with self.assertRaises(ValueError):parse_pipeline(json.dumps(d))

if __name__=='__main__':unittest.main()
