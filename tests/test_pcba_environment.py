"""Device gates, actor boundaries and independent-clock contracts."""
import sys
from pathlib import Path
import time
import unittest
import numpy as np
try:
    import mujoco  # noqa: F401
except ImportError:  # root env; PCBA uses environments/pcba/requirements.txt
    raise unittest.SkipTest('PCBA tests need the isolated PCBA environment')

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environments/pcba'))
from pcba_gym import PCBATestCell, RealtimeSession


class PCBATestCellTests(unittest.TestCase):
    def setUp(self):self.env=PCBATestCell(seed=4)
    def tearDown(self):self.env.close()

    def test_actor_has_sensors_but_no_object_truth_or_latent_result(self):
        obs=self.env.observe()
        self.assertIn('tcp_position_m',obs['robot'])
        self.assertIsNone(obs['fixture']['result'])
        self.assertNotIn('board_positions_m',obs)
        self.assertNotIn('test_receipts',obs)
        self.assertNotIn('seed',obs)
        self.assertNotIn('_outcomes',obs)
        self.assertIn('board_positions_m',self.env.diagnostics())

    def test_invalid_motion_and_empty_fixture_are_atomic(self):
        target=self.env.target.copy()
        for action in ({'delta_xyz_m':[float('nan'),0,0]}, {'delta_xyz_m':[1,0,0]}, {'vacuum':2}):
            with self.assertRaises(ValueError):self.env.command(action)
        receipt=self.env.command({'delta_xyz_m':[.001,0,0],'vacuum':True,'fixture':'close'})
        self.assertFalse(receipt['accepted'])
        np.testing.assert_array_equal(target,self.env.target)
        self.assertFalse(self.env.vacuum)
        self.assertFalse(self.env.command({'fixture':'start_test'})['accepted'])

    def test_vacuum_does_not_grab_a_distant_board(self):
        self.env.command({'vacuum':True});self.env.advance(.2)
        self.assertIsNone(self.env.held)
        self.assertFalse(self.env.observe()['robot']['vacuum_ok'])

    def test_running_tester_blocks_unloading_and_binds_result_to_board(self):
        from pcba_gym.scene import FIXTURE
        import mujoco
        address=self.env.board_qaddrs[0]
        self.env.data.qpos[address:address+3]=FIXTURE
        self.env.data.qpos[address+3:address+7]=[1,0,0,0]
        mujoco.mj_forward(self.env.model,self.env.data)
        self.env.advance(.2)
        self.assertTrue(self.env.command({'fixture':'close'})['accepted'])
        self.env.advance(.3)
        self.assertTrue(self.env.command({'fixture':'start_test'})['accepted'])
        self.assertFalse(self.env.command({'fixture':'open'})['accepted'])
        self.assertIsNone(self.env.observe()['fixture']['result'])
        self.assertFalse(self.env.observe()['fixture']['unload_allowed'])
        self.env.advance(2.)
        self.assertEqual(self.env.observe()['fixture']['result']['board_id'],'PCBA-001')
        self.assertTrue(self.env.command({'fixture':'open'})['accepted'])
        self.env.advance(.3)
        self.assertTrue(self.env.observe()['fixture']['unload_allowed'])

    def test_stale_reply_cannot_change_robot_target(self):
        before=self.env.target.copy();captured=self.env.observe()['capture_time_s']
        self.env.advance(.25)
        receipt=self.env.command({'delta_xyz_m':[.001,0,0]},observed_at_s=captured,ttl_s=.1)
        self.assertFalse(receipt['accepted']);np.testing.assert_array_equal(before,self.env.target)

    def place_for_evaluation(self,board,position):
        import mujoco
        address=self.env.board_qaddrs[board]
        self.env.data.qpos[address:address+3]=position
        self.env.data.qpos[address+3:address+7]=[1,0,0,0]
        dof=int(self.env.model.jnt_dofadr[self.env.model.joint(f'board_joint{board}').id])
        self.env.data.qvel[dof:dof+6]=0
        mujoco.mj_forward(self.env.model,self.env.data)

    def test_conveyor_moves_stops_and_feeds_next_board(self):
        from pcba_gym.scene import FIXTURE, CONVEYOR_STOP
        initial=np.array(self.env.diagnostics()['board_positions_m'])
        self.env.advance(.5)
        moved=np.array(self.env.diagnostics()['board_positions_m'])
        self.assertLess(moved[0,1],initial[0,1]-.01)
        self.env.advance(3.)
        self.assertTrue(self.env.observe()['conveyor']['pickup_ready'])
        stopped=np.array(self.env.diagnostics()['board_positions_m'])
        np.testing.assert_allclose(stopped[0,:2],CONVEYOR_STOP[:2],atol=.005)
        self.env.advance(.5)
        np.testing.assert_allclose(stopped,self.env.diagnostics()['board_positions_m'],atol=.002)
        self.place_for_evaluation(0,FIXTURE)
        self.env.advance(5.)
        self.assertTrue(self.env.observe()['conveyor']['pickup_ready'])
        np.testing.assert_allclose(self.env.diagnostics()['board_positions_m'][1][:2],CONVEYOR_STOP[:2],atol=.005)

    def test_magazine_requires_full_insertion_and_released_rail_support(self):
        from pcba_gym.scene import OUTPUTS
        center=OUTPUTS['PASS'][1]
        self.place_for_evaluation(0,center)
        self.env.advance(.3)
        self.assertTrue(self.env.observe()['outputs']['PASS']['occupied_slots'][1])
        self.assertNotIn(0,self.env.sorted)  # Presence is independent of test/scoring.
        self.env.test_receipts[0]={'status':'PASS'}
        self.place_for_evaluation(0,[center[0],.13,center[2]])
        self.env.advance(.3)
        self.assertNotIn(0,self.env.sorted)
        self.place_for_evaluation(0,center)
        self.env.advance(.3)
        self.assertTrue(self.env.sorted[0]['correct'])
        self.assertEqual(self.env.sorted[0]['slot'],1)
        self.assertEqual(self.env.observe()['outputs']['PASS']['occupied_slots'],[False,True,False])
        # Another board in an occupied slot cannot earn a second sorting credit.
        self.env.test_receipts[1]={'status':'PASS'}
        self.place_for_evaluation(1,center+np.array([0,0,.0016]))
        self.env.advance(.3)
        self.assertNotIn(1,self.env.sorted)

    def test_wrong_magazine_is_scored_as_incorrect(self):
        from pcba_gym.scene import OUTPUTS
        self.env.test_receipts[0]={'status':'FAIL'}
        self.place_for_evaluation(0,OUTPUTS['PASS'][0])
        self.env.advance(.3)
        self.assertFalse(self.env.sorted[0]['correct'])
        self.assertEqual(self.env.score,-1.)

    def test_seeded_reset_reproduces_board_setup(self):
        before=np.array(self.env.diagnostics()['board_positions_m'])
        self.env.advance(.5);self.env.reset(seed=4)
        np.testing.assert_allclose(before,self.env.diagnostics()['board_positions_m'],atol=1e-10)
        self.assertEqual(self.env.test_receipts,{})

    def test_physics_advances_while_policy_is_blocked(self):
        session=RealtimeSession(self.env).start()
        try:
            before=self.env.observe()['capture_time_s'];time.sleep(.25)
            after=self.env.observe()['capture_time_s']
            self.assertGreater(after-before,.15)
            with self.assertRaises(RuntimeError):self.env.step({})
            with self.assertRaises(RuntimeError):self.env.reset()
        finally:session.close()

if __name__=='__main__':unittest.main()
