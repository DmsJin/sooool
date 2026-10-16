"""Pure scheduling checks: no native game, external model or API calls."""
import unittest
from pathlib import Path

from wait_watch import make_watch,schedule_wait,wake_reason


class LatestWaitTests(unittest.TestCase):
    watch_option={'watch_for':{'ball_state':'coming to you','require_in_play':True,'max_steps':80}}

    def test_recorded_long_wait_then_new_brief_wait(self):
        for realtime in (False,True):
            for latest,expected in ((False,1842),(True,1828)):
                wake,watch=schedule_wait(0,None,{'wait_steps':20},5,1822,
                                         latest=latest,legacy_empty_updates=realtime)
                wake,watch=schedule_wait(wake,watch,{'wait_steps':5},5,1823,
                                         latest=latest,legacy_empty_updates=realtime)
                self.assertEqual(wake,expected)
                self.assertIsNone(watch)

    def test_new_nonwatch_wait_cancels_old_watch(self):
        wake,watch=schedule_wait(1900,{'point':5,'deadline':1900},{'wait_steps':5},5,1823,latest=True)
        self.assertEqual(wake,1828)
        self.assertIsNone(watch)

    def test_watch_replaces_deadline_and_uses_public_referee(self):
        wake,watch=schedule_wait(1900,{'point':4,'deadline':1800},self.watch_option,5,1823,latest=True)
        self.assertEqual(wake,1823)
        self.assertEqual(watch,{'point':5,'deadline':1903})
        self.assertIsNone(wake_reason(watch,{'point':5,'ball_state':'going to the opponent'},1824))
        self.assertEqual(wake_reason(watch,{'point':5,'ball_state':'coming to you','ball_in_play':True},1824),
                         'incoming_public_referee')

    def test_default_exact_legacy_values(self):
        oldwatch={'point':5,'deadline':1900}
        for wake in (0,1800,1900):
            for step in (1822,1823):
                for option in ({},{'wait_steps':0},{'wait_steps':5},self.watch_option):
                    for realtime in (False,True):
                        gate=make_watch(option,5,step)
                        expected_wake=max(wake,step+option.get('wait_steps',0)) if realtime or option.get('wait_steps') else wake
                        self.assertEqual(schedule_wait(wake,oldwatch,option,5,step,legacy_empty_updates=realtime),
                                         (expected_wake,gate if gate is not None else oldwatch))

    def test_dispatch_sequence_guards_still_precede_scheduling(self):
        # Inspect the actual dispatch sites without importing native/API runners.
        folder=Path(__file__).parent
        sim=(folder/'simulate.py').read_text();real=(folder/'realtime.py').read_text()
        sim=sim[sim.index('for r in due:'):sim.index('if m.k>=controller_blocked_until and watch is None')]
        real=real[real.index('for request,r in dispatch.ready():'):real.index('dispatch.collect()')]
        self.assertLess(sim.index("if r['seq']<=last:"),sim.index('schedule_wait('))
        self.assertLess(real.index("if p['seq']<=last or p['point']!=point"),real.index('schedule_wait('))


if __name__=='__main__':
    unittest.main()
