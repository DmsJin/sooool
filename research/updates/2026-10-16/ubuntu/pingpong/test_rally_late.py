"""Offline public trajectory fixtures: no native simulator, images/API secrets or model calls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'sports/tabletennis'))
import builtin_players as public
from rally_late import RallyLatePlayer


class RallyLateTests(unittest.TestCase):
    def fixture(self, kind="opponent's return", post=False):
        points, _, bounces = public.rollout(
            np.array([0., -.3, .35]), np.array([0., -1.4, -.4]), .001, 900,
            a_extra=np.array([.1, 0., .2]))
        indices = [10, 30, 50, 70, 90, 110]
        heard = []
        if post:
            indices += [bounces[0] + d for d in (10, 30, 50, 70)]
            heard = [{'event': 'bounce on your half', 't': bounces[0] * .001}]
        leg = {'kind': kind, 'frames': {i * .001: points[i] for i in indices}, 'heard': heard}
        normal, later = public.Player([]), RallyLatePlayer([])
        normal.leg = leg
        later.leg = leg
        return normal, later

    def test_rally_pre_and_post_contact_later(self):
        for post in (False, True):
            with self.subTest(post=post):
                normal, later = self.fixture(post=post)
                old, new = normal.predict(), later.predict()
                self.assertGreater(new[0] - old[0], .1)
                self.assertLess(new[1][1], old[1][1])
                self.assertEqual(new[3:], old[3:])

    def test_preserves_fitted_acceleration_and_bounce_requirement(self):
        for post in (False, True):
            normal, later = self.fixture(post=post)
            with patch.object(public, 'predict_contact', wraps=public.predict_contact) as baseline:
                normal.predict()
                old_args, old_kw = baseline.call_args
            with patch.object(public, 'predict_contact', wraps=public.predict_contact) as changed:
                later.predict()
                new_args, new_kw = changed.call_args
            for old, new in zip(old_args, new_args):
                np.testing.assert_allclose(old, new)
            self.assertGreater(np.linalg.norm(new_args[3]), 1e-6)
            self.assertEqual(old_kw['need_bounce'], new_kw['need_bounce'])
            self.assertFalse(old_kw['late'])
            self.assertTrue(new_kw['late'])

    def test_services_unchanged_before_and_after_bounce(self):
        for post in (False, True):
            normal, later = self.fixture(kind='serve', post=post)
            old, new = normal.predict(), later.predict()
            self.assertEqual(old[0], new[0])
            np.testing.assert_array_equal(old[1], new[1])
            np.testing.assert_array_equal(old[2], new[2])
            self.assertEqual(old[3:], new[3:])

    def test_variant_does_not_modify_public_player(self):
        from candidates import Candidates
        original = public.Player.predict
        base = Candidates({'cameras': []}, mode='geometry_stable_early_chunk')
        variant = Candidates({'cameras': []}, mode='geometry_stable_early_rallylate_chunk')
        self.assertIs(type(base.player), public.Player)
        self.assertIs(type(variant.player), RallyLatePlayer)
        self.assertIs(public.Player.predict, original)


if __name__ == '__main__':
    unittest.main()
