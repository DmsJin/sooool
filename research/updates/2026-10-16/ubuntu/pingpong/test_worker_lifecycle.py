"""Real local subprocess lifetime tests; no native game, model, or API."""
import concurrent.futures as cf
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from worker_lifecycle import ManagedStartup,cancel_workers,identity,matching,publish_process,terminate_owned
from simulate import Pool

HELPERS=Path(__file__).resolve().parent
WORKER='''import sys,time,signal,subprocess,json,os
from pathlib import Path
sys.path.insert(0,HELPER_PATH)
from worker_lifecycle import ManagedStartup
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
startup=ManagedStartup(out/'managed_process.json')
def stop(*args):startup.stop()
signal.signal(signal.SIGTERM,stop)
try:
 with startup:
  child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(3600)','app-server','--stdio'],start_new_session=True)
  (out/'spawned').write_text(str(child.pid))
  if 'initializing' in str(out):time.sleep(3600)
 print(json.dumps({'ready':True,'pid':os.getpid()}),flush=True)
 for line in sys.stdin:time.sleep(3600)
finally:
 signal.signal(signal.SIGTERM,signal.SIG_IGN)
 startup.cleanup()
 (out/'closed').write_text('finally completed')
'''.replace('HELPER_PATH',repr(str(HELPERS)))


def wait_for(path,timeout=5):
    deadline=time.monotonic()+timeout
    while not path.exists() and time.monotonic()<deadline:time.sleep(.01)
    if not path.exists():raise AssertionError('Fixture child did not start')


class WorkerLifecycleTests(unittest.TestCase):
    def test_cancel_during_construction_and_live_turn_only_own_children(self):
        original=subprocess.Popen
        survivor=original([sys.executable,'-c','import time;time.sleep(3600)'],start_new_session=True)
        try:
            for phase in ('initializing','ready'):
                with self.subTest(phase=phase),tempfile.TemporaryDirectory(prefix=phase) as tmp:
                    out=Path(tmp);(out/'source').mkdir();(out/'source/native_worker.py').write_text(WORKER)
                    def local_worker(args,**kwargs):return original([sys.executable,*args[1:]],**kwargs)
                    with patch('simulate.subprocess.Popen',side_effect=local_worker):
                        pool=Pool(out,1,cancel_tail=True)
                        future=pool.submit('unused','',out/'decision')
                        wait_for(out/'native_0/spawned')
                        record=json.loads((out/'native_0/managed_process.json').read_text())
                        pool.close(screen_stop=True)
                    self.assertTrue((out/'native_0/closed').exists())
                    self.assertFalse(matching(record))
                    self.assertTrue(future.done())
                    self.assertIsNone(survivor.poll())
                    with self.assertRaisesRegex(RuntimeError,'stopped'):
                        pool.request('no new spawn','',out/'later')
        finally:survivor.terminate();survivor.wait(timeout=2)

    def test_queued_work_is_cancelled(self):
        with tempfile.TemporaryDirectory() as tmp:
            pool=Pool(Path(tmp),1,cancel_tail=True)
            gate=__import__('threading').Event()
            running=pool.pool.submit(gate.wait)
            queued=pool.pool.submit(lambda:'must not execute')
            with cf.ThreadPoolExecutor(max_workers=1) as closer:
                closed=closer.submit(pool.close,screen_stop=True)
                deadline=time.monotonic()+2
                while not queued.cancelled() and time.monotonic()<deadline:time.sleep(.01)
                gate.set();closed.result(timeout=3)
            self.assertTrue(queued.cancelled())
            self.assertTrue(running.done())

    def test_stop_inside_popen_still_publishes_and_cleans_child(self):
        original=subprocess.Popen
        with tempfile.TemporaryDirectory() as tmp:
            startup=ManagedStartup(Path(tmp)/'owner.json')
            def interrupting_spawn(*args,**kwargs):
                process=original(*args,**kwargs)
                startup.stop() # same handler action, in the Popen ownership gap
                return process
            with patch('worker_lifecycle.subprocess.Popen',side_effect=interrupting_spawn):
                try:
                    with self.assertRaises(SystemExit),startup:
                        subprocess.Popen([sys.executable,'-c','import time;time.sleep(3600)','app-server','--stdio'],start_new_session=True)
                finally:startup.cleanup()
            self.assertEqual(len(startup.processes),1)
            self.assertIsNotNone(startup.processes[0].returncode)
            self.assertTrue(startup.path.exists())

    def test_non_screen_errors_remain_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            pool=Pool(Path(tmp),1,cancel_tail=True)
            def fail():raise TimeoutError('actual active model failure')
            future=pool.pool.submit(fail)
            pool.close(screen_stop=False)
            with self.assertRaisesRegex(TimeoutError,'active model failure'):future.result()
            self.assertFalse(pool.stopping)

    def test_identity_mismatch_refuses_to_signal_live_unrelated_process(self):
        p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(3600)'],start_new_session=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                record=publish_process(p,Path(tmp)/'owner.json');record['start_ticks']-=1
                with self.assertRaisesRegex(RuntimeError,'unverifiable'):terminate_owned(record,0)
                self.assertIsNone(p.poll())
        finally:p.terminate();p.wait(timeout=2)

    def test_owned_group_kill_fallback(self):
        p=subprocess.Popen([sys.executable,'-c','import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print("ready",flush=True);time.sleep(3600)'],stdout=subprocess.PIPE,text=True,start_new_session=True)
        try:
            self.assertEqual(p.stdout.readline().strip(),'ready')
            with tempfile.TemporaryDirectory() as tmp:
                record=publish_process(p,Path(tmp)/'owner.json');terminate_owned(record,grace_s=.05)
                p.wait(timeout=2);self.assertFalse(matching(record))
        finally:
            if p.poll() is None:p.kill();p.wait()
            p.stdout.close()

if __name__=='__main__':unittest.main()
