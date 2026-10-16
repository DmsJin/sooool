import unittest
from concurrent.futures import Future
from research.policies import make_prompt
from research.scheduler import VirtualScheduler

class RollingProtocolTests(unittest.TestCase):
    def prompt(self,config,profile=None):
        return make_prompt('tracking_dodge_safe_intercept_v2',
            {'image_frames':[0,30,60],'held':[4,1,1,0]},config,
            profile or {'p50_s':2.4,'p95_s':3.2},[[4,1,1,0,48]])

    def test_opt_in_description_preserves_rest_and_original_action_input(self):
        base={'decision_fanout':1,'capacity':4,'wait_for_move':False,'wait_for_winner':False}
        before=self.prompt(base);after=self.prompt({**base,'rolling_observations':True})
        added=[line for line in after.splitlines(keepends=True) if line.startswith('Controller protocol: rolling')]
        self.assertEqual(len(added),1)
        self.assertEqual(after.replace(added[0],''),before)
        self.assertIn('another in-flight answer may change them',added[0])
        self.assertIn('Known returned plan: [[4,1,1,0,48]]',after)
        self.assertNotIn('at most one request',after)

    def test_wrong_runtime_cannot_claim_rolling_protocol(self):
        for config in ({'capacity':1},{'capacity':4,'decision_fanout':4},
                       {'capacity':4,'wait_for_move':True},{'capacity':4,'wait_for_winner':True}):
            with self.assertRaises(ValueError):self.prompt({**config,'rolling_observations':True})

    def test_modeled_serial_samples_are_not_claimed_concurrent_measurements(self):
        text=self.prompt({}, {'kind':'modeled_independent_k1_pipeline_from_historical_serial_terminal','p50_s':2.4,'p95_s':3.2})
        self.assertIn('not measured concurrent performance',text)
        self.assertIn('readiness and slot release coincide',text)
        self.assertNotIn('Observed screenshot-to',text)

    def test_newer_answer_interrupts_plan_and_old_answer_uses_slot_until_due(self):
        def answer(move,duration):
            f=Future();f.set_result({'plan':[[move,1,1,0,duration]]});return f
        scheduler=VirtualScheduler(capacity=3)
        scheduler.submit(0,answer(4,48),30)
        scheduler.advance(6);scheduler.submit(6,answer(3,48),6)
        events=scheduler.advance(12)
        self.assertEqual(events[0]['disposition'],'applied')
        self.assertEqual(scheduler.action_at(12),[3,1,1,0])
        self.assertEqual(scheduler.inflight,1)
        scheduler.submit(12,answer(0,1),6)
        events=scheduler.advance(18)
        self.assertEqual(events[0]['disposition'],'applied')
        self.assertEqual(scheduler.action_at(18),[0,1,1,0])
        events=scheduler.advance(30)
        self.assertEqual(events[0]['disposition'],'stale')
        self.assertEqual(scheduler.inflight,0)
        self.assertEqual(scheduler.action_at(30),[0,1,1,0])

if __name__=='__main__':unittest.main()
