"""Staggered capture timing, compact output contract and the virtual-clock simulator."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
try:
    import mujoco  # noqa: F401
except ImportError:  # root env; PCBA uses environments/pcba/requirements.txt
    raise unittest.SkipTest('PCBA tests need the isolated PCBA environment')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environments/pcba'))
from pcba_gym.pipeline import request_due, latency_quantile, parse_image_size, pipeline_schema, parse_pipeline


def due(**kw):
    args={'now':10.,'active_end':None,'outstanding':0,'oldest_pending_age':0.,'concurrency':1,
          'latency_samples':[],'default_latency':8.}
    args.update(kw);return request_due(**args)


class StaggerTests(unittest.TestCase):
    def test_idle_robot_requests_immediately_once(self):
        self.assertTrue(due())
        self.assertFalse(due(outstanding=1))

    def test_idle_hedge_only_after_slow_first_request(self):
        self.assertFalse(due(concurrency=2,outstanding=1,oldest_pending_age=5.))
        self.assertTrue(due(concurrency=2,outstanding=1,oldest_pending_age=9.))

    def test_executing_chunk_captures_one_latency_before_end(self):
        self.assertFalse(due(now=10.,active_end=20.))      # 10 s left > 8 s latency
        self.assertTrue(due(now=12.,active_end=20.))       # reply should land as the chunk ends

    def test_two_lanes_hedge_pessimistic_then_fresher(self):
        samples=[6.,7.,8.,9.,10.]
        first=dict(concurrency=2,active_end=30.,latency_samples=samples)
        self.assertTrue(due(now=30.-latency_quantile(samples,.8,8.),**first))
        self.assertFalse(due(now=30.-latency_quantile(samples,.8,8.)-.1,**first))
        self.assertFalse(due(now=21.5,outstanding=1,**first))
        self.assertTrue(due(now=30.-latency_quantile(samples,.4,8.),outstanding=1,**first))
        self.assertFalse(due(now=29.,outstanding=2,**first))

    def test_capture_waits_for_the_result_of_a_chained_test(self):
        from pcba_gym.pipeline import awaiting_result
        chunk={'actions':[{'delta_xyz_m':[0,0,0],'delta_yaw_rad':0,'fixture':'start_test'}],'result_id_at_start':'T-0001'}
        self.assertTrue(awaiting_result(chunk,{'result':{'test_id':'T-0001'}}))
        self.assertFalse(awaiting_result(chunk,{'result':{'test_id':'T-0002'}}))
        self.assertFalse(awaiting_result({'actions':[{'delta_xyz_m':[0,0,0],'delta_yaw_rad':0}],'result_id_at_start':None},{'result':None}))
        self.assertFalse(awaiting_result(None,{'result':None}))

    def test_measured_latency_replaces_default_after_three_replies(self):
        self.assertEqual(latency_quantile([5.,5.],.5,8.),8.)
        self.assertEqual(latency_quantile([5.,5.,5.],.5,8.),5.)

    def test_image_size_bounds(self):
        self.assertEqual(parse_image_size('480x360'),(480,360))
        with self.assertRaises(ValueError):parse_image_size('64x48')


class LeanOutputTests(unittest.TestCase):
    def test_lean_schema_only_tightens_text_lengths(self):
        full=pipeline_schema('full');lean=pipeline_schema('lean')
        self.assertEqual(lean['properties']['memory']['maxLength'],160)
        self.assertEqual(lean['properties']['summary']['maxLength'],100)
        for schema in (full,lean):
            for key in ('memory','summary'):schema['properties'][key].pop('maxLength')
        self.assertEqual(full,lean)

    def test_lean_reply_still_parses_as_literal_actions(self):
        reply={'summary':'Wait above pick zone.','memory':'B3 at y=-0.10, contact ~41.2s.','done':False,
            'start_guard':{'vacuum_ok':None,'fixture_board_present':None,'clamp_state':None,'tester_state':None,'result_test_id':None},
            'segments':[{'delta_xyz_m':[0,0,0],'delta_yaw_rad':0,'repeat':20,'vacuum':None,'fixture':None}]}
        _,actions=parse_pipeline(json.dumps(reply));self.assertEqual(len(actions),20)


class CalibrationTests(unittest.TestCase):
    def test_top_calibration_matches_camera_projection(self):
        import re,mujoco,numpy as np
        from pcba_gym.loop import PCBALoopCell
        from pcba_gym.pipeline import top_calibration_text
        env=PCBALoopCell(seed=0)
        try:
            text=top_calibration_text(env.model,640,480)
            a,x0,y0=(float(v) for v in re.search(r'world_x = ([0-9.]+)\*u ([-+][0-9.]+); world_y = ([0-9.]+)',text).groups())
            data=mujoco.MjData(env.model);mujoco.mj_forward(env.model,data)
            for world in ((-.36,-.14),(-.36,.14),(0.,-.08),(.29,.21)):
                c=data.cam_xmat[env.model.camera('top').id].reshape(3,3).T@(np.r_[world,.8008]-data.cam_xpos[env.model.camera('top').id])
                f=240/np.tan(np.deg2rad(env.model.cam_fovy[env.model.camera('top').id])/2)
                u,v=320+f*c[0]/-c[2],240-f*c[1]/-c[2]
                self.assertAlmostEqual(a*u+x0,world[0],places=3);self.assertAlmostEqual(y0-a*v,world[1],places=3)
        finally:env.close()

    def test_wrist_calibration_recovers_grasp_offset_and_yaw(self):
        import re,mujoco,numpy as np
        from pcba_gym.loop import PCBALoopCell
        from pcba_gym.pipeline import wrist_calibration_text
        env=PCBALoopCell(seed=0)
        try:
            text=wrist_calibration_text(env.model,640,480)
            scale=float(re.search(r'TCP height\) 1 px = ([0-9.]+) mm',text).group(1))/1000
            edge=float(re.search(r'horizontal line at v=([0-9]+)',text).group(1))
            data=mujoco.MjData(env.model);mujoco.mj_forward(env.model,data)
            cid=env.model.camera('wrist').id;tcp=data.site_xpos[env.model.site('tcp').id];R=data.xmat[env.model.body('tool').id].reshape(3,3)
            f=240/np.tan(np.deg2rad(env.model.cam_fovy[cid])/2)
            def proj(p):
                c=data.cam_xmat[cid].reshape(3,3).T@(p-data.cam_xpos[cid]);return np.array([320+f*c[0]/-c[2],240-f*c[1]/-c[2]])
            for dx,dy,th in ((.0,.0,.0),(.004,-.006,.0),(-.003,.005,.12),(.006,.002,-.25)):
                rot=np.array([[np.cos(th),-np.sin(th)],[np.sin(th),np.cos(th)]])
                centre=np.r_[dx,dy]
                ends=[centre+rot@np.r_[sx*.055,-.0375] for sx in (-1,1)]
                pix=[proj(tcp+R@np.r_[e,0.]) for e in ends];mid=(pix[0]+pix[1])/2
                yaw=-np.arctan((pix[1][1]-pix[0][1])/(pix[1][0]-pix[0][0]))
                est_dx=(mid[0]-320)*scale-.0375*np.sin(yaw);est_dy=(edge-mid[1])*scale-.0375*(1-np.cos(yaw))
                self.assertAlmostEqual(yaw,th,places=2)
                self.assertLess(abs(est_dx-dx),.0006);self.assertLess(abs(est_dy-dy),.0006)
        finally:env.close()

    def test_adaptive_cameras_follow_public_signals(self):
        from pcba_gym.pipeline import select_cameras
        far={'robot':{'vacuum_ok':False,'tcp_position_m':[-.36,0.,.9]}}
        held={'robot':{'vacuum_ok':True,'tcp_position_m':[-.36,0.,.9]}}
        near={'robot':{'vacuum_ok':False,'tcp_position_m':[.02,-.07,.85]}}
        self.assertEqual(select_cameras('adaptive',far),('top',))
        self.assertEqual(select_cameras('adaptive',held),('top','wrist'))
        self.assertEqual(select_cameras('adaptive',near),('top','wrist'))
        waiting={'robot':{'vacuum_ok':False,'tcp_position_m':[-.37,.10,.804]}}
        high={'robot':{'vacuum_ok':False,'tcp_position_m':[-.37,.10,.95]}}
        self.assertEqual(select_cameras('adaptive',waiting),('top','wrist'))
        self.assertEqual(select_cameras('adaptive',high),('top',))

    def test_lean2_uses_lean_schema(self):
        self.assertEqual(pipeline_schema('lean2'),pipeline_schema('lean'))


class TimedStartTests(unittest.TestCase):
    def packet(self,start_at):
        return {'sequence':5,'parent_revision':1,'requires_parent_success':False,'capture_wall':10.,'capture_time_s':10.,
                'expected_start_pose_m_rad':[0.,0.,1.,0.],
                'decision':{'start_at_s':start_at,'start_guard':{k:None for k in ('vacuum_ok','fixture_board_present','clamp_state','tester_state','result_test_id')}}}

    def obs(self,now):
        return {'capture_time_s':now,'robot':{'commanded_tcp_pose_m_rad':[0.,0.,1.,0.],'vacuum_ok':False},
                'fixture':{'board_present':False,'clamp_state':'open','tester_state':'idle','result':None}}

    def test_model_start_time_is_forwarded_or_rejected_never_shifted(self):
        from pcba_gym.pipeline import rejection
        args=dict(revision=1,parent_success=True,latest_selected=4,ttl=12.)
        self.assertIsNone(rejection(self.packet(15.),observation=self.obs(14.),wall_now=14.,**args))
        self.assertEqual(rejection(self.packet(13.),observation=self.obs(14.),wall_now=14.,**args),'late_start')
        self.assertEqual(rejection(self.packet(21.8),observation=self.obs(14.),wall_now=14.,**args),'start_beyond_ttl')
        self.assertIsNone(rejection(self.packet(None),observation=self.obs(14.),wall_now=14.,**args))

    def test_parser_accepts_optional_start_time(self):
        reply={'summary':'s','memory':'m','done':False,'start_at_s':12.5,
            'start_guard':{k:None for k in ('vacuum_ok','fixture_board_present','clamp_state','tester_state','result_test_id')},
            'segments':[{'delta_xyz_m':[0,0,0],'delta_yaw_rad':0,'repeat':2,'vacuum':None,'fixture':None}]}
        d,_=parse_pipeline(json.dumps(reply));self.assertEqual(d['start_at_s'],12.5)
        reply['start_at_s']='soon'
        with self.assertRaises(ValueError):parse_pipeline(json.dumps(reply))

    def test_timed_schema_requires_start_time(self):
        self.assertIn('start_at_s',pipeline_schema('lean7')['required'])
        self.assertNotIn('start_at_s',pipeline_schema('lean5')['properties'])


class TimedClient:
    """Asks every chunk to start 3 s after its capture; no subscription calls."""
    def __init__(self,**kwargs):pass
    def act(self,prompt,images,directory):
        import re
        now=float(re.search(r'"capture_time_s":([0-9.]+)',prompt).group(1))
        reply={'summary':'Timed hold.','memory':'m','done':False,'start_at_s':now+3.,
            'start_guard':{'vacuum_ok':None,'fixture_board_present':None,'clamp_state':None,'tester_state':None,'result_test_id':None},
            'segments':[{'delta_xyz_m':[0,0,0],'delta_yaw_rad':0,'repeat':10,'vacuum':None,'fixture':None}]}
        return json.dumps(reply),{'wall_seconds':.01,'token_usage':{'last':{'outputTokens':5,'reasoningOutputTokens':0}},'stages_s':None}
    def close(self):pass


class FakeClient:
    """Deterministic stand-in: no subscription calls, zero-motion waits."""
    def __init__(self,**kwargs):self.calls=0
    def act(self,prompt,images,directory):
        self.calls+=1;assert 'COMPACT OUTPUT CONTRACT' in prompt and len(images)==1
        reply={'summary':'Hold.','memory':'m','done':False,
            'start_guard':{'vacuum_ok':None,'fixture_board_present':None,'clamp_state':None,'tester_state':None,'result_test_id':None},
            'segments':[{'delta_xyz_m':[0,0,0],'delta_yaw_rad':0,'repeat':60,'vacuum':None,'fixture':None}]}
        usage={'last':{'outputTokens':50,'reasoningOutputTokens':0}}
        return json.dumps(reply),{'wall_seconds':.01,'token_usage':usage,'stages_s':None}
    def close(self):pass


class SimulateTests(unittest.TestCase):
    def test_virtual_clock_delivers_at_sampled_delay_and_keeps_literal_execution(self):
        import runtime.subscription as subscription
        from pcba_gym import simulate
        original=subscription.SubscriptionClient;subscription.SubscriptionClient=FakeClient
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile=Path(tmp)/'profile.json';profile.write_text(json.dumps({'samples_s':[2.,2.,2.,2.,2.]}))
                report=simulate.simulate_pipeline(Path(tmp)/'run',profile=profile,sim_duration=12.,max_calls=6,
                    image_size=(320,240),expected_latency=2.)
        finally:subscription.SubscriptionClient=original
        m=report['metrics'];chunks=report['chunks']
        self.assertEqual(report['kind'],'subscription_simulation_virtual_clock')
        self.assertGreaterEqual(m['selected_chunks'],3)
        # A reply is only usable at capture + sampled delay on the virtual clock.
        for c in report['calls']:
            if 'selected_s' in c:self.assertGreaterEqual(c['selected_s']+1e-9,c['capture_s']+2.)
        # Staggering: later captures happen while the previous chunk is still executing.
        self.assertTrue(any(c['issued_while_executing'] for c in report['calls']))
        self.assertLess(m['wait_between_chunks_s']['max'],.2)
        self.assertTrue(all(cmd['receipt']['accepted'] for c in chunks for cmd in c['execution']['commands']))


class TimedSimulateTests(unittest.TestCase):
    def test_simulated_chunks_wait_for_the_model_start_time(self):
        import runtime.subscription as subscription
        from pcba_gym import simulate
        original=subscription.SubscriptionClient;subscription.SubscriptionClient=TimedClient
        try:
            with tempfile.TemporaryDirectory() as tmp:
                profile=Path(tmp)/'profile.json';profile.write_text(json.dumps({'samples_s':[2.,2.,2.,2.,2.]}))
                report=simulate.simulate_pipeline(Path(tmp)/'run',profile=profile,sim_duration=12.,max_calls=4,
                    image_size=(320,240),expected_latency=2.,output_mode='lean7')
        finally:subscription.SubscriptionClient=original
        calls={c['sequence']:c for c in report['calls']}
        self.assertTrue(report['chunks'])
        for chunk in report['chunks']:
            first=chunk['execution']['commands'][0]['applied_at_sim_s']
            self.assertGreaterEqual(first+1e-9,calls[chunk['sequence']]['capture_s']+3.)


if __name__=='__main__':unittest.main()
