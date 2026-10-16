import unittest
from concurrent.futures import Future
from research.scheduler import VirtualScheduler, parse_plan


def done(answer):
    future = Future()
    future.set_result(answer)
    return future


class SchedulerTest(unittest.TestCase):
    def test_no_early_application_and_capacity(self):
        scheduler = VirtualScheduler(1)
        self.assertEqual(scheduler.submit(0, done('[2,1,1,0,4]'), 5), 0)
        self.assertIsNone(scheduler.submit(0, done('[3,0,0,0,4]'), 1))
        scheduler.advance(4)
        self.assertEqual(scheduler.action_at(4), [0,0,0,0])
        self.assertEqual(scheduler.advance(5)[0]['status'], 'applied')
        self.assertEqual(scheduler.action_at(5), [2,1,1,0])
        self.assertTrue(scheduler.available(5))

    def test_out_of_order_old_response_ignored(self):
        scheduler = VirtualScheduler(8)
        scheduler.submit(0, done('[2,1,1,0,20]'), 10)
        scheduler.advance(2)
        scheduler.submit(2, done('[3,1,0,0,20]'), 2)
        scheduler.advance(4)
        self.assertEqual(scheduler.action_at(4)[0], 3)
        self.assertEqual(scheduler.advance(10)[0]['status'], 'stale')
        self.assertEqual(scheduler.action_at(10)[0], 3)

    def test_new_response_clears_old_chunk_suffix_and_expires(self):
        scheduler = VirtualScheduler(4)
        scheduler.submit(0, done('[[2,1,1,1,3],[3,1,1,0,20]]'), 0)
        scheduler.advance(0)
        self.assertEqual(scheduler.action_at(0), [2,1,1,1])
        scheduler.advance(1)
        scheduler.submit(1, done('[4,1,0,0,2]'), 0)
        scheduler.advance(1)
        self.assertEqual(scheduler.action_at(1), [4,1,0,0])
        scheduler.advance(3)
        self.assertEqual(scheduler.action_at(3), [0,1,0,0])
        scheduler.advance(20)
        self.assertEqual(scheduler.action_at(20), [0,1,0,0])

    def test_future_wait_is_at_virtual_due_frame(self):
        class FakeFuture:
            called = False
            def result(self):
                self.called = True
                return '[1,1,0,0,10]'
        future = FakeFuture()
        scheduler = VirtualScheduler()
        scheduler.submit(0, future, 10)
        scheduler.advance(9)
        self.assertFalse(future.called)
        scheduler.advance(10)
        self.assertTrue(future.called)

    def test_invalid_does_not_replace_valid_plan(self):
        scheduler = VirtualScheduler(4)
        scheduler.submit(0, done('[2,1,1,0,20]'), 0)
        scheduler.advance(0)
        scheduler.advance(1)
        scheduler.submit(1, done('[99,1,1,0,10]'), 1)
        self.assertEqual(scheduler.advance(2)[0]['status'], 'invalid')
        self.assertEqual(scheduler.action_at(2)[0], 2)

    def test_strict_bounds(self):
        for bad in ('[0,1,1,0,0]', '[0,1,1,0,121]', '[true,1,1,0,10]',
                    '{"action":[0,1,1,0,10]}', '[[0,1,1,0,1]]'*5):
            with self.assertRaises((ValueError, TypeError)):
                parse_plan(bad)
        self.assertEqual(parse_plan({'answer':'[0,1,1,0,120]','meta':{},'plan':[]})[0].duration, 120)


if __name__ == '__main__':
    unittest.main()
