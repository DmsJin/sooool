"""Pure public trajectory and own-state fixtures; no native world or requests."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'sports/tabletennis'))
import builtin_players as public
from robot_contact import RobotContactPlayer,comfortable_contact,receive_target,audit_contact_boundary


class RobotContactTests(unittest.TestCase):
    def flight(self):
        fit=(0.,np.array([0.,-.3,.35]),np.array([0.,-1.4,-.4]),np.array([.1,0.,.2]))
        points,velocities,bounces=public.rollout(*fit[1:3],.001,1600,a_extra=fit[3])
        return fit,points,velocities,bounces

    def test_latest_future_comfortable_height_before_second_bounce(self):
        fit,points,velocities,bounces=self.flight();base=[0.,-1.45];now=.1
        result=comfortable_contact(fit,base,now,True)
        self.assertIsNotNone(result)
        t,p,v=result
        self.assertGreater(t,bounces[0]*.001)
        self.assertLess(t,bounces[1]*.001)
        self.assertGreaterEqual(t,now+.04)
        self.assertGreaterEqual(p[2],.20)
        self.assertLessEqual(abs(p[0]-base[0]),.22)
        self.assertLessEqual(abs(p[1]-(base[1]+.45)),.10)
        allowed=[i for i in range(bounces[0]+1,bounces[1]) if i*.001>=now+.04 and points[i,2]>=.20
                 and abs(points[i,0]-base[0])<=.22 and abs(points[i,1]-(base[1]+.45))<=.10]
        self.assertAlmostEqual(t,max(allowed)*.001)
        np.testing.assert_array_equal(v,velocities[max(allowed)])
        self.assertIsNone(comfortable_contact(fit,base,t,True))
        self.assertIsNone(comfortable_contact(fit,[2.,-1.55],now,True))

    def test_public_fit_acceleration_forwarded_and_observed_bounce(self):
        fit,points,velocities,bounces=self.flight();i=bounces[0]+20
        post=(i*.001,points[i],velocities[i],fit[3])
        with patch.object(public,'rollout',wraps=public.rollout) as rollout:
            result=comfortable_contact(post,[0.,-1.45],.3,False)
        np.testing.assert_array_equal(rollout.call_args.kwargs['a_extra'],fit[3])
        self.assertIsNotNone(result)
        self.assertLess(result[0],bounces[1]*.001+.005)
        # An observed bounce can arrive before three post-bounce camera frames;
        # keep using the pre-bounce fit, skipping the bounce already in the past.
        pre=comfortable_contact(fit,[0.,-1.45],.3,True)
        self.assertIsNotNone(pre)
        self.assertGreater(pre[0],bounces[0]*.001)
        self.assertLess(pre[0],bounces[1]*.001)

    def test_rally_fallback_and_services_identical(self):
        fit,points,_,_=self.flight()
        frames={i*.001:points[i] for i in (10,30,50,70,90,110)}
        normal=public.Player([]);robot=RobotContactPlayer([])
        for kind in ('serve',"opponent's return"):
            leg={'kind':kind,'frames':frames,'heard':[]}
            normal.leg=leg;robot.leg=leg;robot.observed_base=np.array([2.,-1.55]);robot.observed_time=.11
            old,new=normal.predict(),robot.predict()
            self.assertEqual(old[0],new[0]);self.assertEqual(old[3:],new[3:])
            np.testing.assert_array_equal(old[1],new[1]);np.testing.assert_array_equal(old[2],new[2])
            if kind=='serve':self.assertIsNone(robot.contact_metadata)
            else:self.assertTrue(robot.contact_metadata['fallback'])

    def test_optional_midbase_and_default_player(self):
        from candidates import Candidates
        for mode,y in [('geometry_chunk',-1.55),('geometry_latebase_chunk',-1.79),('geometry_midbase_chunk',-1.67)]:
            self.assertEqual(receive_target(mode).tolist(),[0.,y])
        with patch('candidates.serve_plan',return_value=None):
            base=Candidates({'cameras':[]},'geometry_chunk')
            robot=Candidates({'cameras':[]},'geometry_robotcontact_midbase_chunk')
        self.assertIs(type(base.player),public.Player)
        self.assertIs(type(robot.player),RobotContactPlayer)
        view={'state':{'step':1,'point':1,'base_xy':[0.,-1.55],'base_rest':[0.,-1.67],
                       'ball_state':'going to the opponent','ball_in_play':False},'observation':{}}
        with patch('candidates.serve_plan',return_value=None):
            mid=Candidates({'cameras':[]},'geometry_midbase_rallywatch_chunk')
        self.assertEqual(len([o for o in mid.build(view,{}) if 'watch_for' in o]),1)
        view['state']['base_rest']=[0.,-1.55]
        options=mid.build(view,{})
        self.assertFalse([o for o in options if 'watch_for' in o])
        self.assertEqual(next(o['action']['base'] for o in options if o['kind']=='move'),[0.,-1.67])

    def test_heard_bounce_before_predicted_bounce_still_requires_crossing(self):
        fit,points,_,bounces=self.flight()
        robot=RobotContactPlayer([])
        robot.leg={'kind':"opponent's return",'frames':{i*.001:points[i] for i in (10,30,50)},
                   'heard':[{'event':'bounce on your half','t':.08}]}
        robot.observed_base=np.array([0.,-.95]);robot.observed_time=.1
        with patch.object(public,'fit_flight',return_value=fit),patch('robot_contact.comfortable_contact',wraps=comfortable_contact) as select:
            robot.predict()
        self.assertTrue(select.call_args.args[3])
        audit=audit_contact_boundary(fit,'pre',.15,.1)
        self.assertTrue(audit['before_required_bounce'])
        self.assertGreater(audit['required_bounce_game_s'],.1)

    def test_post_fit_does_not_skip_second_bounce_already_in_past(self):
        fit=(0.,np.array([0.,-.3,1.]),np.array([0.,-.8,-.4]),np.array([.1,0.,.2]))
        points,velocities,bounces=public.rollout(*fit[1:3],.001,2400,a_extra=fit[3])
        i=bounces[0]+20;post=(i*.001,points[i],velocities[i],fit[3]);now=bounces[1]*.001+.02
        self.assertIsNone(comfortable_contact(post,[0.,-1.55],now,False))
        audit=audit_contact_boundary(post,'post',1.565,now)
        self.assertTrue(audit['at_or_after_second_bounce'])


if __name__=='__main__':unittest.main()
