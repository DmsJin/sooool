import concurrent.futures as cf
import unittest
from simulate import Scheduler
from simulate_async import FutureScheduler
class Tests(unittest.TestCase):
 def test_results_never_apply_before_virtual_due(self):
  f=cf.Future();f.set_result({'chosen':4});s=FutureScheduler();s.submit(0,0,f,8,8)
  self.assertEqual(s.advance(7),0);self.assertEqual(s.advance(8),4)
 def test_stale_unfinished_computation_does_not_block_new_action(self):
  old=cf.Future();new=cf.Future();new.set_result({'chosen':3});s=FutureScheduler()
  s.submit(0,0,old,8,8);s.submit(4,1,new,4,4)
  self.assertEqual(s.advance(8),3);self.assertFalse(old.done())
 def test_fixed_actions_identical_to_serial_scheduler(self):
  serial=Scheduler();parallel=FutureScheduler()
  for frame in range(200):
   self.assertEqual(serial.advance(frame),parallel.advance(frame))
   if frame%4==0 and serial.available(frame) is not None:
    seq=frame//4;action=seq%9;delay=(seq*13)%25+1
    f=cf.Future();f.set_result({'chosen':action})
    serial.submit(frame,seq,action,delay,delay);parallel.submit(frame,seq,f,delay,delay)
  self.assertEqual(serial.applied,parallel.applied)
if __name__=='__main__':unittest.main()
