import unittest
from hop_controller_v3 import HopControllerV3


def r(seq,obs,action):return {'seq':seq,'obs_frame':obs,'chosen':action}


class RowFreshnessTests(unittest.TestCase):
    def test_recorded_old_row_left_cannot_drive_into_new_row_enemy(self):
        c=HopControllerV3()
        self.assertEqual(c.advance(184,[r(43,172,1)]),1)
        self.assertEqual(c.advance(188,[]),0)
        self.assertEqual(c.advance(191,[r(45,180,3)]),0)
        self.assertEqual(c.advance(202,[r(47,188,5)]),5)
        self.assertEqual(c.advance(206,[]),0)

    def test_diagonal_landing_releases_horizontal_too(self):
        c=HopControllerV3()
        self.assertEqual(c.advance(447,[r(109,436,6)]),6)
        self.assertEqual(c.advance(450,[]),6)
        self.assertEqual(c.advance(451,[]),0)
        self.assertEqual(c.advance(452,[r(110,440,3)]),0)
        self.assertEqual(c.advance(469,[r(113,452,5)]),5)

    def test_active_hop_is_atomic_for_stale_horizontal_and_noop_replies(self):
        c=HopControllerV3();c.advance(10,[r(0,0,7)])
        self.assertEqual(c.advance(11,[r(1,4,0)]),7)
        self.assertEqual(c.advance(12,[r(2,8,3)]),7)
        self.assertEqual(c.advance(14,[]),0)

    def test_fresh_horizontal_command_continues_until_replaced(self):
        c=HopControllerV3();c.advance(10,[r(0,0,1)])
        self.assertEqual(c.advance(20,[r(1,16,2)]),2)
        self.assertEqual(c.advance(80,[]),2)
        self.assertEqual(c.advance(81,[r(2,76,0)]),0)

    def test_stale_sequence_is_consumed_and_older_reply_never_overrides(self):
        c=HopControllerV3();c.advance(10,[r(1,4,1)]);c.advance(14,[])
        self.assertEqual(c.advance(20,[r(4,12,3)]),0)
        self.assertEqual(c.last,4)
        self.assertEqual(c.ignored[-1]['seq'],4)
        self.assertNotIn(4,[event['seq'] for event in c.applied])
        self.assertEqual(c.advance(21,[r(3,8,2)]),0)

    def test_observation_at_finished_frame_is_fresh(self):
        c=HopControllerV3();c.advance(10,[r(0,0,1)])
        self.assertEqual(c.advance(20,[r(1,14,4)]),4)
        self.assertEqual(c.advance(24,[]),0)


if __name__=='__main__':unittest.main()
