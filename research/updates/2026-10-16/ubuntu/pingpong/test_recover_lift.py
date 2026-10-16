"""Public-state recovery gates and installation lifecycle; no native/model/API."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'sports/tabletennis'))
from recover_lift import Recovery,eligible,option,reply_installed
from candidates import Candidates,menu_prompt


def state():
    return {'point':5,'step':150,'you_serve':True,'ball_state':'your serve','ball_in_play':False,
            'serve':{'phase':'open','deadline_in_s':4.59},'command':'none (ready)',
            'q':[.3751,-1.5992,.5,0,0,0,0,0,0],'base_xy':[.3751,-1.5992],
            'base_rest':[.2,-1.87],'paddle_pos':[.643,-1.034,.087],
            'paddle_normal':[.074,.987,-.142]}


class RecoverTests(unittest.TestCase):
    def test_fixed_relative_effect_time_and_normal(self):
        s=state();o=option(s,[0]*7,0);b=o['action']
        self.assertNotIn('contact_step',o)
        self.assertEqual(b['t'],2.0);self.assertEqual(b['pos'],[.643,-1.034,.35])
        self.assertEqual(b['base'],s['base_xy']);self.assertEqual(b['vel'],[0,0,0])
        self.assertAlmostEqual(sum(x*x for x in b['normal']),1)
        self.assertEqual(o['purpose'],'recoverlift')

    def test_stage_and_threshold_boundaries(self):
        self.assertTrue(eligible(state(),[0]*7,0))
        for change in [lambda s:s.update(ball_in_play=True),lambda s:s.update(you_serve=False),
                       lambda s:s['serve'].update(phase='tossed'),lambda s:s['serve'].update(deadline_in_s=3.199),
                       lambda s:s.update(step=99),lambda s:s['q'].__setitem__(2,.1),
                       lambda s:s['paddle_pos'].__setitem__(2,.2),lambda s:s.update(command={'phase':'approach'}),
                       lambda s:s.update(base_rest=[0,-1.75])]:
            s=state();change(s);self.assertFalse(eligible(s,[0]*7,0))
        self.assertFalse(eligible(state(),[0]*7,0,used=True))

    def test_delivery_drift_stage_point_deadline_and_settling(self):
        s=state();b=option(s,[0]*7,0)['action'];r=Recovery()
        self.assertTrue(r.delivery_allowed(s,b,[]))
        for change in [lambda s:s.update(point=6),lambda s:s['base_xy'].__setitem__(0,.5),
                       lambda s:s['paddle_pos'].__setitem__(1,-.9),lambda s:s['serve'].update(deadline_in_s=3),
                       lambda s:s.update(command={'phase':'follow_through'})]:
            changed=copy.deepcopy(s);change(changed);self.assertFalse(r.delivery_allowed(changed,b,[]))
        self.assertFalse(r.delivery_allowed(s,b,[{'step':100,'action':{'type':'move','base':[0,-1.75]}}]))

    def test_only_success_consumes_point_and_active_wait_gate(self):
        s=state();b=option(s,[0]*7,0)['action'];r=Recovery()
        r.mark(b,False);self.assertTrue(r.delivery_allowed(s,b,[]))
        r.mark(b,True);self.assertFalse(r.delivery_allowed(s,b,[]))
        for phase in ('approach','follow_through'):
            s['command']={key:b[key] for key in ('pos','normal','vel')};s['command']['phase']=phase
            self.assertTrue(r.blocked(s))
        s['command']='none (ready)';self.assertFalse(r.blocked(s))
        s['point']=6;b2={**b,'_recoverlift_point':6}
        self.assertTrue(r.delivery_allowed(s,b2,[]))

    def test_public_reply_install_proof(self):
        b=option(state(),[0]*7,0)['action']
        command={key:b[key] for key in ('pos','normal','vel')};command.update(phase='approach',contact_in_s=1.9)
        reply={'took_effect':{'step':150,'stroke':{'n_swing_steps':100}},'now':{'step':160,'point':5,'command':command}}
        self.assertTrue(reply_installed(reply,b))
        for change in [lambda d:d['took_effect']['stroke'].update(n_swing_steps=0),
                       lambda d:d['now'].update(point=6),lambda d:d['now']['command'].update(contact_in_s=.5),
                       lambda d:d.update(http_status=409)]:
            d=copy.deepcopy(reply);change(d);self.assertFalse(reply_installed(d,b))

    def test_default_parity_and_wait_only_until_natural_rest(self):
        def menu(mode):
            with patch('candidates.serve_plan',return_value=None):return Candidates({'cameras':[]},mode)
        base=menu('geometry_stable_chunk');opt=menu('geometry_stable_recoverlift_chunk')
        initial=state();initial.update(step=0);initial['q'][2]=0
        base.build({'state':copy.deepcopy(initial),'observation':{}},{})
        opt.build({'state':copy.deepcopy(initial),'observation':{}},{})
        s=state();v={'state':copy.deepcopy(s),'observation':{}}
        expected=base.build(copy.deepcopy(v),{});actual=opt.build(copy.deepcopy(v),{})
        self.assertEqual(expected,actual[:-1]);self.assertEqual(actual[-1]['purpose'],'recoverlift')
        b=actual[-1]['action'];s['recent_applied']=[{'action':b,'_recoverlift_installed':True}]
        s['command']={key:b[key] for key in ('pos','normal','vel')};s['command']['phase']='follow_through'
        self.assertTrue(all(o['kind']=='wait' for o in opt.build({'state':s,'observation':{}},{})))
        s['command']='none (ready)'
        self.assertFalse(any(o.get('purpose')=='recoverlift' for o in opt.build({'state':s,'observation':{}},{})))
        view={'state':state(),'observation':{}}
        self.assertNotIn('If a recovery lift',menu_prompt(view,[],{},'geometry_stable_chunk'))

if __name__=='__main__':unittest.main()
