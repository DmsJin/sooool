import unittest,inspect
from executor import Executor
from policy import parse,visible
class Boundaries(unittest.TestCase):
 def test_expired_issue_plan_brakes_and_skips_elapsed(self):
  e=Executor();e.offer([[3,.1,1],[2,.3,1],[3,0,1]],0,1.5,5,'issue')
  self.assertEqual(e.due(1.5),{'type':'drive','speed':2,'steering':.3})
  self.assertEqual(e.due(2),{'type':'drive','speed':3,'steering':0})
  self.assertEqual(e.due(3),{'type':'none'})
  self.assertIsNone(e.due(4))
 def test_frozen_output_has_no_camera_feedback(self):
  self.assertEqual(list(inspect.signature(Executor.offer).parameters),['self','commands','issued','arrived','seq','anchor'])
  a,b=Executor(),Executor();commands=[[2,.12,.7]]
  for e in [a,b]:e.offer(commands,0,1,1,'arrival')
  images={'yellow_left':object(),'yellow_right':object()}
  self.assertEqual([a.due(t) for t in [1,1.5,1.7]],[b.due(t) for t in [1,1.5,1.7]])
 def test_older_model_response_cannot_override_newer(self):
  e=Executor();e.offer([[2,.1,1]],0,1,4,'arrival')
  self.assertFalse(e.offer([[4,-.4,1]],0,1,3,'arrival'))
  self.assertEqual(e.due(1),{'type':'drive','speed':2,'steering':.1})
 def test_strict_actuator_types_and_state_whitelist(self):
  for text in ['[["2",0,1]]','[[2,NaN,1]]','[[2,0,0]]','[[2,0.49,1]]','[[true,0,1]]']:
   with self.assertRaises(ValueError):parse(text,1,'arrival')
  self.assertEqual(visible({'own':{'forward_speed':1},'camera_measurements':{'ground_path':[]},'position':[1,2],'seed':101}),{'own':{'forward_speed':1}})
if __name__=='__main__':unittest.main()
