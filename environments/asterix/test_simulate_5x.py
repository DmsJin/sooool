import concurrent.futures as cf
import unittest
from simulate_5x import delay_frames, select_images, VirtualQueue, base_prompt
from hop_controller_v2 import HopControllerV2


def answer(action):
    f = cf.Future(); f.set_result({'chosen':action}); return f


class FiveTimesClockTests(unittest.TestCase):
    def test_default_prompt_matches_current_executor_and_v4_retains_horizontal(self):
        default=base_prompt('policy',[1.28],1.)
        self.assertEqual(default,base_prompt('policy',[1.28],1.,'v3'))
        self.assertIn('ALL movement components release to NOOP',default)
        self.assertIn('ENTIRE stale command is ignored',default)
        v4=base_prompt('policy',[1.28],1.,'v4')
        self.assertIn('retains its LEFT/RIGHT component',v4)
        self.assertNotIn('ALL movement components release to NOOP',v4)

    def test_delay_uses_twelve_raw_fps_and_scales_before_rounding(self):
        self.assertEqual(delay_frames(.9),11)
        self.assertEqual(delay_frames(1.28),16)
        self.assertEqual(delay_frames(1.28,1.25),20)
        self.assertEqual(delay_frames(7.56975),91)
        for bad in [0,-1,float('nan'),float('inf')]:
            with self.assertRaises(ValueError): delay_frames(bad)

    def test_causal_history_and_startup_deduplication(self):
        self.assertEqual(select_images([(0,b'a')]),[(0,b'a')])
        self.assertEqual([f for f,_ in select_images([(i,b'a') for i in range(0,36,4)])],[0,24,32])
        self.assertEqual([f for f,_ in select_images([(i,b'a') for i in range(4,40,4)])],[4,28,36])

    def test_capacity_and_out_of_order_completions(self):
        q,c = VirtualQueue(2),HopControllerV2()
        q.submit(0,0,answer(2),20)
        q.submit(4,1,answer(3),2)
        self.assertIsNone(q.available(5))
        self.assertEqual(q.advance(6,c),3)
        self.assertIsNotNone(q.available(6))
        self.assertEqual(q.advance(20,c),3)
        self.assertEqual(q.peak,2)

    def test_superseded_native_future_does_not_block_newest_due_reply(self):
        q,c = VirtualQueue(2),HopControllerV2()
        unresolved = cf.Future()
        q.submit(0,0,unresolved,10)
        q.submit(4,1,answer(3),6)
        self.assertEqual(q.advance(10,c),3)
        self.assertFalse(unresolved.done())


if __name__ == '__main__': unittest.main()
