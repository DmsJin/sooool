import unittest

from experiments.rhythm.sparse_scheduler import SparseActionScheduler


class SparseSchedulerTests(unittest.TestCase):
    def test_revision_preserves_unmentioned_future(self):
        s = SparseActionScheduler()
        s.submit('old', 0, [[0, 500], [1, 600]], 0)
        s.submit('new', 100, [[0, 410]], 150)
        self.assertEqual([(a.lane, a.game_ms) for a in s.pending()], [(0, 510), (1, 600)])

    def test_repeated_same_hit_and_empty_frame_do_not_duplicate_or_cancel(self):
        s = SparseActionScheduler()
        s.submit('old', 0, [[0, 500]], 0)
        s.submit('new', 100, [[0, 400]], 150)
        s.submit('empty', 200, [], 250, horizon_ms=1800, lanes=[0, 1, 2, 3])
        self.assertEqual([a.game_ms for a in s.pending()], [500])
        self.assertEqual(len(s.advance(500)), 1)

    def test_old_reply_cannot_replace_fresh_same_target_but_can_add_distinct_target(self):
        s = SparseActionScheduler()
        s.submit('fresh', 100, [[0, 400]], 150, horizon_ms=1800, lanes=[0, 1])
        s.submit('stale', 0, [[0, 510], [1, 700]], 200, horizon_ms=1800, lanes=[0, 1])
        self.assertEqual(s.rejected_stale, 1)
        self.assertEqual([(a.lane, a.game_ms) for a in s.pending()], [(0, 500), (1, 700)])

    def test_empty_newer_frame_does_not_block_unmatched_old_detection(self):
        s = SparseActionScheduler()
        s.submit('empty-new', 100, [], 150, horizon_ms=1800, lanes=[0, 1, 2, 3])
        s.submit('old-visible', 0, [[0, 500]], 200)
        self.assertEqual([a.game_ms for a in s.pending()], [500])

    def test_newer_distinct_eighth_does_not_block_older_unmatched_note(self):
        s = SparseActionScheduler()
        s.submit('new-note', 100, [[0, 665]], 150)
        s.submit('old-note', 0, [[0, 500]], 200)
        self.assertEqual([a.game_ms for a in s.pending()], [500, 765])

    def test_executed_duplicate_rejected_but_eighth_note_retained(self):
        s = SparseActionScheduler()
        s.submit('first', 0, [[0, 100]], 0)
        s.acknowledge(0, 100, 100)
        s.submit('next', 100, [[0, 100], [0, 265]], 110)
        self.assertEqual(s.rejected_refractory, 1)
        self.assertEqual([a.game_ms for a in s.pending()], [365])

    def test_distinct_eighth_notes_are_not_merged(self):
        s = SparseActionScheduler()
        s.submit('r', 0, [[0, 500], [0, 765]], 0)
        self.assertEqual([a.game_ms for a in s.pending()], [500, 765])

    def test_commit_race_keeps_valid_old_hit_when_new_prediction_is_late(self):
        s = SparseActionScheduler()
        s.submit('old', 5550, [[2, 7080.449251 - 5550]], 6778.493)
        s.advance(7078.382001)
        s.submit('new', 5850, [[2, 7077.953411 - 5850]], 7078.382001)
        self.assertEqual([a.game_ms for a in s.pending()], [7080.449251])
        s.submit('near', 5860, [[2, 7082 - 5860]], 7079)
        self.assertEqual(s.rejected_committed, 1)
        self.assertEqual(len(s.advance(7080.449251)), 1)


if __name__ == '__main__':
    unittest.main()
