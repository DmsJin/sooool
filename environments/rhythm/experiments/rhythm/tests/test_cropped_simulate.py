import unittest

from experiments.rhythm.cropped_simulate import apply_late_grace
from experiments.rhythm.sparse_scheduler import SparseActionScheduler


class LateGraceTests(unittest.TestCase):
    def test_late_grace_uses_arrival_time_and_never_backdates(self):
        actions = [[0, 100], [1, 145], [2, 200]]
        adjusted = apply_late_grace(actions, 1000, 1200, 55)
        self.assertEqual(adjusted, [[1, 200], [2, 200]])
        scheduler = SparseActionScheduler()
        accepted = scheduler.submit('r', 1000, adjusted, 1200, horizon_ms=1855)
        self.assertEqual([action.game_ms for action in accepted], [1200, 1200])
        self.assertTrue(all(action.game_ms >= 1200 for action in accepted))

    def test_future_target_is_preserved_and_older_than_grace_is_dropped(self):
        self.assertEqual(apply_late_grace([[0, 144], [1, 300]], 1000, 1200, 55), [[1, 300]])


if __name__ == '__main__':
    unittest.main()
