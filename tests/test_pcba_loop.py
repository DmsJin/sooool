"""Physical loop contract, deadlines and actor visibility."""
from pathlib import Path
import sys
import unittest
import numpy as np
try:
    import mujoco  # noqa: F401
except ImportError:  # root env; PCBA uses environments/pcba/requirements.txt
    raise unittest.SkipTest('PCBA tests need the isolated PCBA environment')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environments/pcba'))
from pcba_gym.loop import PCBALoopCell,path_at,nearest_path,LENGTH,DEADLINE
from pcba_gym.runner import policy_prompt


class LoopTests(unittest.TestCase):
    def test_path_is_closed_and_projection_is_continuous(self):
        for s in np.linspace(0,LENGTH,257):
            p,t=path_at(s);actual,projected,tangent=nearest_path(p)
            np.testing.assert_allclose(projected,p,atol=1e-9)
            np.testing.assert_allclose(tangent,t,atol=1e-9)
            self.assertAlmostEqual(np.linalg.norm(t),1.)
        np.testing.assert_allclose(path_at(0)[0],path_at(LENGTH)[0])

    def test_public_calibration_does_not_leak_tracking_or_results(self):
        e=PCBALoopCell(seed=0)
        try:
            o=e.observe();p=policy_prompt(o,0,'',None,12)
            self.assertTrue(o['conveyor']['running'])
            self.assertIn('continuously circulating',p)
            self.assertNotIn('pick a stopped board',p)
            for private in ('board_positions_m','board_yaw_rad','distance_m','unpicked_laps','lane_offsets','test_receipts'):
                self.assertNotIn(private,o)
                self.assertNotIn('"'+private+'":',p)
            self.assertIsNone(o['fixture']['result'])
            one=policy_prompt(o,0,'',None,12,camera_names=('top',))
            self.assertIn('Camera input order: top.',one)
            self.assertNotIn('Camera order: overview, overhead/top, wrist.',one)
            self.assertGreater(max(abs(v) for v in e.diagnostics()['board_yaw_rad']),.2)
        finally:e.close()

    def test_task_deadline_is_independent_of_command_expiry(self):
        e=PCBALoopCell()
        try:
            e.data.time=e._loop_started+DEADLINE-.01;e.advance(.02)
            self.assertEqual(e.diagnostics()['loop']['deadline_missed'],list(range(5)))
            # A freshly stamped command remains syntactically admissible; it
            # cannot undo a task failure that has already been recorded.
            self.assertTrue(e.command({},observed_at_s=e.data.time,ttl_s=.5)['accepted'])
            self.assertEqual(len(e.diagnostics()['loop']['deadline_missed']),5)
            self.assertTrue(e.step({})[3])
        finally:e.close()

    def test_motion_and_reset_are_seeded_without_an_end_stop(self):
        e=PCBALoopCell(seed=2)
        try:
            before=np.array(e.diagnostics()['board_positions_m']);e.advance(1.)
            after=np.array(e.diagnostics()['board_positions_m'])
            expected=set()
            for c in e.data.contact[:e.data.ncon]:
                a,b=int(c.geom1),int(c.geom2)
                if a in e._slab_ids and b in e._belt_ids:expected.add(e._slab_ids[a])
                if b in e._slab_ids and a in e._belt_ids:expected.add(e._slab_ids[b])
            e._drive_conveyor()
            self.assertEqual(e._contact_boards,expected)
            self.assertTrue(np.all(np.linalg.norm(after[:,:2]-before[:,:2],axis=1)>.02))
            self.assertTrue(e.observe()['conveyor']['running'])
            e.reset(2)
            np.testing.assert_allclose(before,e.diagnostics()['board_positions_m'],atol=1e-9)
            self.assertFalse(e.diagnostics()['dropped'])
        finally:e.close()

if __name__=='__main__':unittest.main()
