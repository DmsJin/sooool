"""Policy boundary, literal action scheduling, and live inference contracts."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock
import numpy as np
try:
    import mujoco  # noqa: F401
except ImportError:  # root env; PCBA uses environments/pcba/requirements.txt
    raise unittest.SkipTest('PCBA tests need the isolated PCBA environment')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environments/pcba'))
from pcba_gym import PCBATestCell, RealtimeSession
from pcba_gym.runner import parse_decision, policy_prompt, execute_chunk


def decision(**kw):
    s={'delta_xyz_m':[.001,0,0],'delta_yaw_rad':0.,'repeat':3,'vacuum':None,'fixture':None}
    s.update(kw)
    return json.dumps({'summary':'Move along X.','memory':'Contact not reached.','done':False,'segments':[s]})


class PolicyTests(unittest.TestCase):
    def test_unconfirmed_requested_tier_fails_before_inference(self):
        from runtime.subscription import SubscriptionClient
        for tier in ('ultrafast','priority'):
            with tempfile.TemporaryDirectory() as directory:
                c=SubscriptionClient.__new__(SubscriptionClient)
                c.output=c.workspace=Path(directory);c.counter=0;c.service_tier=tier
                c.quota=Mock(return_value={})
                c._rpc=Mock(return_value={'model':'gpt-6.1-sol','reasoningEffort':'low',
                    'serviceTier':None,'thread':{'id':'fake'}})
                with self.assertRaisesRegex(RuntimeError,'did not confirm'):
                    c.act('No request should be sent.',[])
                self.assertEqual([call.args[0] for call in c._rpc.call_args_list],['thread/start'])

    def test_literal_repeat_and_null_device_commands(self):
        _,actions=parse_decision(decision())
        self.assertEqual(len(actions),3)
        self.assertEqual(actions,[{'delta_xyz_m':[.001,0,0],'delta_yaw_rad':0.}]*3)
        self.assertNotIn('vacuum',actions[0])

    def test_whole_chunk_rejects_invalid_limits_and_repeated_fixture(self):
        for kw in ({'repeat':121},{'repeat':True},{'fixture':'start_test'},
                   {'delta_xyz_m':[float('nan'),0,0]},{'delta_xyz_m':[.03,0,0]},
                   {'vacuum':1},{'delta_yaw_rad':float('inf')}):
            with self.assertRaises(ValueError):parse_decision(decision(**kw))

    def test_prompt_cannot_include_evaluator_or_future_outcomes(self):
        env=PCBATestCell()
        try:
            obs=env.observe();obs['diagnostics']={'board_positions_m':'SECRET_POSE'}
            obs['_outcomes']='SECRET_RESULT';obs['images']={'top':'RAW_BYTES_NOT_TEXT'}
            text=policy_prompt(obs,0,'',None,12)
            for secret in ('SECRET_POSE','SECRET_RESULT','RAW_BYTES_NOT_TEXT','diagnostics'):
                self.assertNotIn(secret,text)
            self.assertIn('commanded_tcp_pose_m_rad',text)
        finally:env.close()

    def test_expired_wall_observation_executes_no_motion(self):
        env=PCBATestCell();before=env.target.copy()
        try:
            _,actions=parse_decision(decision())
            with tempfile.TemporaryFile(mode='w+') as log:
                r=execute_chunk(env,actions,capture_time=env.data.time,capture_wall=time.monotonic()-2,
                    ttl=.5,stop=threading.Event(),log=log)
            self.assertEqual(r['accepted_commands'],0)
            self.assertEqual(r['last_receipt']['reason'],'expired_wall_observation')
            np.testing.assert_array_equal(env.target,before)
        finally:env.close()

    def test_literal_execution_preserves_live_clock_and_action_values(self):
        env=PCBATestCell();session=RealtimeSession(env).start();before=env.target.copy()
        try:
            observed=env.observe()['capture_time_s'];wall=time.monotonic()
            # A delayed model does not pause physics.
            time.sleep(.15);self.assertGreater(env.data.time-observed,.1)
            _,actions=parse_decision(decision())
            with tempfile.TemporaryFile(mode='w+') as log:
                r=execute_chunk(env,actions,capture_time=observed,capture_wall=wall,
                    ttl=2.,stop=threading.Event(),log=log)
            self.assertEqual(r['accepted_commands'],3)
            np.testing.assert_allclose(env.target,before+np.array([.003,0,0,0]),atol=1e-12)
            self.assertGreater(env.data.time-observed,.2)
        finally:session.close();env.close()

    def test_rejected_device_command_aborts_remainder_without_moving(self):
        env=PCBATestCell();before=env.target.copy()
        try:
            action={'fixture':'start_test','delta_xyz_m':[.001,0,0]}
            with tempfile.TemporaryFile(mode='w+') as log:
                r=execute_chunk(env,[action,{'delta_xyz_m':[.001,0,0]}],
                    capture_time=env.data.time,capture_wall=time.monotonic(),ttl=2.,stop=threading.Event(),log=log)
            self.assertEqual(r['accepted_commands'],0);self.assertEqual(len(r['commands']),1)
            np.testing.assert_array_equal(env.target,before)
        finally:env.close()

if __name__=='__main__':unittest.main()
