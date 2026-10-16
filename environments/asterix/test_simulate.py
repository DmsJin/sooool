import unittest
from simulate import Scheduler,parse_action
class Tests(unittest.TestCase):
 def test_stale_response_never_overwrites_newer(self):
  s=Scheduler();s.submit(0,0,1,8,8);s.submit(1,1,2,3,3)
  self.assertEqual(s.advance(4),2);self.assertEqual(s.advance(8),2)
 def test_capacity_and_held_action(self):
  s=Scheduler(2);s.submit(0,0,3,8,8);s.submit(0,1,4,9,9)
  self.assertIsNone(s.available(4));self.assertEqual(s.advance(7),0)
  self.assertEqual(s.advance(8),3);self.assertIsNotNone(s.available(8))
 def test_newest_of_same_frame(self):
  s=Scheduler();s.submit(0,0,1,8,8);s.submit(4,1,2,4,4);self.assertEqual(s.advance(8),2)
 def test_invalid_actions_rejected(self):
  self.assertEqual(parse_action('3'),3)
  for text in ('true','9','{"action":true}','{"action":3,"x":1}'):
   with self.assertRaises(ValueError):parse_action(text)
if __name__=='__main__':unittest.main()
