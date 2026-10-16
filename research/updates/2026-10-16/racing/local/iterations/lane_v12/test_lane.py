import unittest
from lane import Lane,parse_lane
class LaneContract(unittest.TestCase):
 def test_goals_expire_and_lost_stripe_brakes(self):
  c=Lane();c.offer([[3.2,.38,2]],None,10,7,1000)
  self.assertEqual(c.drive(11,{}),{'type':'none'})
  self.assertEqual(c.drive(13,{'ground_path':[[2,0]]}),{'type':'none'})
 def test_only_model_selects_lane_and_obstacles_do_not_override_it(self):
  c=Lane();c.offer([[3.2,.38,2]],None,0,0,0)
  view={'ground_path':[[2,0]],'magenta_ground_bounds':{'x_near':1,'y_min':0,'y_max':1}}
  left=c.drive(1,view);self.assertGreater(left['steering'],0)
  view['magenta_ground_bounds']['y_min']=-1
  self.assertEqual(left,c.drive(1,view))
  c.offer([[3.2,-.38,2]],None,0,1,0)
  self.assertLess(c.drive(1,view)['steering'],0)
 def test_invalid_or_nonfinite_model_goal_rejected(self):
  for text in ['[[4.1,0,2]]','[[3,1,2]]','[[3,0,0]]','[[3,NaN,2]]','[[3,0,2],[3,0,2]]']:
   with self.assertRaises((ValueError,TypeError)):parse_lane(text)
if __name__=='__main__':unittest.main()
