"""Public-state gate availability, prompt and wake fixtures; no native world or calls."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'sports/tabletennis'))
from candidates import Candidates,menu_prompt
from wait_watch import make_watch,wake_reason


class RallyWatchTests(unittest.TestCase):
    def options(self,mode,ball='going to the opponent',rest=-1.55):
        state={'step':100,'point':1,'base_xy':[0.,-1.55],
               'ball_state':ball,'ball_in_play':False,'you_serve':False,'you_receive_serve':True}
        if rest is not None:state['base_rest']=[0.,rest]
        view={'state':state,'observation':{}}
        with patch('candidates.serve_plan',return_value=None):
            menu=Candidates({'cameras':[]},mode)
        opts=menu.build(view,{})
        return view,opts,[o for o in opts if 'watch_for' in o]

    def test_outgoing_only_and_receive_target(self):
        for mode,target in [('geometry_rallywatch_chunk',-1.55),
                            ('geometry_rallywatch_latebase_chunk',-1.79)]:
            self.assertEqual(len(self.options(mode,rest=target)[2]),1)
            for ball,rest in [('your serve',target),('coming to you',target),
                              ('dead',target),('going to the opponent',None),
                              ('going to the opponent',-1.65)]:
                self.assertFalse(self.options(mode,ball,rest)[2])
        self.assertFalse(self.options('geometry_rallywatch_latebase_chunk',rest=-1.55)[2])
        self.assertFalse(self.options('geometry_chunk')[2])

    def test_legacy_watch_still_watches_opponent_service(self):
        self.assertEqual(len(self.options('geometry_watch_chunk','dead')[2]),1)
        self.assertFalse(self.options('geometry_rallywatch_chunk','dead')[2])

    def test_prompt_and_existing_public_wake(self):
        view,opts,gates=self.options('geometry_rallywatch_chunk')
        prompt=menu_prompt(view,opts,{},'geometry_rallywatch_chunk')
        self.assertIn('Experimental rally observation scheduling',prompt)
        self.assertNotIn('Experimental rally observation scheduling',menu_prompt(view,opts,{},'geometry_chunk'))
        watch=make_watch(gates[0],1,100)
        self.assertIsNone(wake_reason(watch,{'point':1,'ball_state':'going to the opponent','ball_in_play':True},110))
        self.assertIsNone(wake_reason(watch,{'point':1,'ball_state':'coming to you','ball_in_play':False},110))
        self.assertEqual(wake_reason(watch,{'point':1,'ball_state':'coming to you','ball_in_play':True},110),'incoming_public_referee')
        self.assertEqual(wake_reason(watch,{'point':1},180),'maximum_wait_elapsed')
        self.assertEqual(wake_reason(watch,{'point':2},101),'point_changed')


if __name__=='__main__':unittest.main()
