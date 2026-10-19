"""Authoritative physics survives a Python-busy policy/renderer process."""
from pathlib import Path
import sys
import tempfile
import time
import unittest
try:
    import mujoco  # noqa: F401
except ImportError:  # root env; PCBA uses environments/pcba/requirements.txt
    raise unittest.SkipTest('PCBA tests need the isolated PCBA environment')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'environments/pcba'))
from pcba_gym.process_clock import ProcessCell,ProcessSession


class ProcessClockTests(unittest.TestCase):
    def test_clock_command_routing_and_snapshot_boundary(self):
        with tempfile.TemporaryDirectory(prefix='pcba-process-test-') as assets:
            env=ProcessCell(layout='loop',seed=0,asset_dir=assets)
            session=ProcessSession(env).start()
            try:
                before=env.observe()['capture_time_s'];end=time.monotonic()+1.
                # This work shares no GIL with the authoritative physics process.
                while time.monotonic()<end:sum(range(1000))
                obs=env.observe();after=obs['capture_time_s']
                self.assertGreater(after-before,.75)
                self.assertNotIn('qpos',obs);self.assertNotIn('board_positions_m',obs)
                self.assertFalse(env.command({},observed_at_s=before,ttl_s=.1)['accepted'])
                self.assertTrue(env.command({'vacuum':True})['accepted'])
                self.assertTrue(env.observe()['robot']['vacuum_on'])
                env.sync_snapshot();self.assertGreaterEqual(env.data.time,after)
            finally:session.close()
            try:
                frozen=env.observe()['capture_time_s'];time.sleep(.05)
                self.assertEqual(frozen,env.observe()['capture_time_s'])
                self.assertGreater(session.timing()['sim_elapsed_s'],.75)
            finally:env.close()

if __name__=='__main__':unittest.main()
