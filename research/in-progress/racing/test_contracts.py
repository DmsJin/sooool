import concurrent.futures as cf
import importlib.util
import json
import pathlib
import tempfile
import sys,math
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from waypoints import Ego,Tracker,parse_points
import unittest

spec=importlib.util.spec_from_file_location('research',pathlib.Path(__file__).with_name('run.py'))
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class Contracts(unittest.TestCase):
 def test_actions_reject_nonfinite_and_out_of_range(self):
  for text in ['[[4.1,0,.2]]','[[1,NaN,.2]]','[[1,0,0]]','[[1,0,.2],[1,0,.2]]']:
   with self.assertRaises((ValueError,TypeError)):r.parse(text)
  self.assertEqual(r.parse('[[2,0.12,0.2]]'),[[2,.12,.2]])

 def test_global_budget_includes_other_workers_inflight(self):
  with tempfile.TemporaryDirectory() as d:
   path=pathlib.Path(d)/'budget.json'
   # Independent instances are what separate episode processes use.
   def reserve(_):
    try:return r.Budget(path).reserve('x',[b'image']*3,'profile',6)
    except RuntimeError:return None
   with cf.ThreadPoolExecutor(max_workers=24) as pool:ids=[x for x in pool.map(reserve,range(40)) if x]
   data=json.loads(path.read_text())
   self.assertLessEqual(sum(x['usd'] for x in data['reserved'].values()),6)
   self.assertTrue(0<len(ids)<40)
   for ident in ids:r.Budget(path).settle(ident,None)
   settled=json.loads(path.read_text())
   self.assertFalse(settled['reserved'])
   self.assertGreater(settled['charged_upper_usd'],0)
   self.assertLessEqual(settled['charged_upper_usd'],6)

 def test_delayed_plan_skips_elapsed_commands(self):
  commands=[[2,.2,1],[3,.1,1],[3,0,1]]
  plan=r.schedule_commands(commands,100,250,.01,'issue')
  self.assertEqual(plan,[(250,{'type':'drive','speed':3,'steering':.1}),(300,{'type':'drive','speed':3,'steering':0})])
  self.assertEqual(r.schedule_commands(commands,100,400,.01,'issue'),[(400,{'type':'none'})])
  self.assertEqual(r.schedule_commands(commands,100,250,.01,'arrival')[0],(250,{'type':'drive','speed':2,'steering':.2}))

 def test_waypoint_frame_and_expiration(self):
  ego=Ego();tracker=Tracker(ego)
  tracker.offer([[2,0,3],[4,0,3],[6,0,3]],ego.pose(),0,7,0)
  ego.update(3,0,1)
  self.assertEqual(tracker.local_points(),[(-1,0,3),(1,0,3),(3,0,3)])
  self.assertEqual(tracker.drive(1,3),{'type':'drive','speed':3,'steering':0})
  self.assertEqual(tracker.drive(3,3),{'type':'none'})
  ego.yaw=math.pi/2
  self.assertAlmostEqual(tracker.local_points()[-1][1],-3)
  with self.assertRaises(ValueError):parse_points('[[2,0,3],[4,NaN,3],[6,0,3]]')

 def test_unknown_error_does_not_refund_cost(self):
  with tempfile.TemporaryDirectory() as d:
   b=r.Budget(pathlib.Path(d)/'budget.json');ident=b.reserve('x',[],'profile',6)
   b.settle(ident,None)
   self.assertGreater(json.loads(b.path.read_text())['charged_upper_usd'],0)

if __name__=='__main__':unittest.main()
