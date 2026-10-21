"""The showcase skin is render-only: it must not change what a recorded state replays."""
from pathlib import Path
import sys
import tempfile
import unittest
import numpy as np
try:
    import mujoco
except ImportError:  # root env; PCBA uses environments/pcba/requirements.txt
    raise unittest.SkipTest('PCBA tests need the isolated PCBA environment')

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'environments/pcba'))
from pcba_gym.loop import build_loop_scene
from pcba_gym.showcase import interp_qpos, seg_spans, _joint_layout
from pcba_gym.showcase_scene import skin_scene


class ShowcaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        (root / 'scene.xml').write_text(build_loop_scene(root / 'assets'))
        cls.plain = mujoco.MjModel.from_xml_path(str(root / 'scene.xml'))
        cls.skinned = mujoco.MjModel.from_xml_string(skin_scene(root / 'scene.xml', root / 'art'))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_state_layout_is_unchanged(self):
        for field in ('nq', 'nv', 'nu', 'neq', 'njnt', 'nbody'):
            self.assertEqual(getattr(self.plain, field), getattr(self.skinned, field), field)

    def test_collision_geometry_is_unchanged(self):
        def colliders(m):
            return sorted(m.geom(i).name for i in range(m.ngeom) if m.geom_contype[i] or m.geom_conaffinity[i])
        self.assertEqual(colliders(self.plain), colliders(self.skinned))
        added = [self.skinned.geom(i).name for i in range(self.skinned.ngeom) if self.skinned.geom(i).name.startswith('show_')]
        self.assertTrue(added)
        for name in added:
            g = self.skinned.geom(name)
            self.assertEqual((int(g.contype[0]), int(g.conaffinity[0]), int(g.bodyid[0])), (0, 0, 0))

    def test_recorded_qpos_replays_to_same_poses(self):
        rng = np.random.default_rng(0)
        q = self.plain.qpos0.copy(); q[:4] += rng.normal(0, .2, 4)
        poses = []
        for m in (self.plain, self.skinned):
            d = mujoco.MjData(m); d.qpos[:] = q; mujoco.mj_kinematics(m, d)
            poses.append(np.array([d.xpos[m.body(f'board{i}').id] for i in range(5)] + [d.site_xpos[m.site('tcp').id]]))
        np.testing.assert_allclose(poses[0], poses[1], atol=1e-12)

    def test_interpolation_keeps_unit_quaternions_and_holds_gaps(self):
        free, scalar = _joint_layout(self.plain)
        q0 = self.plain.qpos0.copy(); q1 = q0.copy(); q1[scalar] += .1
        a = free[0]; q1[a + 3:a + 7] = [0, 0, 0, 1]
        states = {'qpos': np.stack([q0, q1, q1])}
        q, i = interp_qpos(states, np.array([0., .1, 5.]), .05, free, scalar)
        self.assertEqual(i, 0)
        np.testing.assert_allclose(q[scalar], q0[scalar] + .05)
        self.assertAlmostEqual(np.linalg.norm(q[a + 3:a + 7]), 1.)
        held, _ = interp_qpos(states, np.array([0., .1, 5.]), 2., free, scalar)
        np.testing.assert_allclose(held, q1)

    def test_segment_spans_cover_each_raw_segment(self):
        raw = ('{"summary":"x","segments":[{"delta_xyz_m":[0,0,0],"repeat":2},'
               '{"delta_xyz_m":[0.01,0,0],"repeat":3}],"start_at_s":null}')
        spans = seg_spans(raw)
        self.assertEqual([raw[a:b] for a, b in spans],
                         ['{"delta_xyz_m":[0,0,0],"repeat":2}', '{"delta_xyz_m":[0.01,0,0],"repeat":3}'])


if __name__ == '__main__':
    unittest.main()
