"""Pure strict-prefix/action reconstruction checks; no native world or model."""
import copy
import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from rally_fork import prefix_before,prefix_actions,replay_high_prefix,verify_public_observation


def rows():
    action={'type':'act','pos':[0,-1.7,.4],'normal':[0,1,0],'vel':[0,1,1]}
    selected={'kind':'act','contact_step':90,'action':action}
    return [{'ev':'model_issued','seq':1,'k':10,'options':[selected]},
            {'ev':'model_visible','seq':1,'k':20,'answer':'{"choice":0}'},
            {'ev':'cmd','k':20,'seat':'A','cmd':{'type':'traj','q':[[1]]}},
            {'ev':'effect','k':20,'seq':1,'info':{'T_from_now':.7},'result':{'command':'traj'}},
            {'ev':'model_issued','seq':2,'k':25,'options':[]}]


class FakeMatch:
    def __init__(self):self.k=0;self.dt=.01;self.applies=[]
    def step(self):self.k+=1
    def observe(self,seat):return {'point':3}
    def apply(self,seat,low):self.applies.append(low);return {'command':'traj'}
    def resume(self):pass


class HighReplayTests(unittest.TestCase):
    def test_strict_prefix_no_future_answer(self):
        r=rows();prefix,target=prefix_before(r,2)
        self.assertEqual(len(prefix_actions(prefix)),1)
        r[1]['ev']='not_visible'
        r.append({'ev':'model_visible','seq':1,'answer':'{"choice":0}'})
        prefix,_=prefix_before(r,2)
        with self.assertRaisesRegex(ValueError,'already-visible'):prefix_actions(prefix)

    def test_precise_contact_time_not_rounded_feedback(self):
        r=rows();r[0]['options'][0]['contact_step']=55;r[3]['info']['T_from_now']=.35
        body=prefix_actions(r[:4])[2]['body']
        self.assertEqual(body['t'],35*.01)
        self.assertNotEqual(body['t'],.35)
        r[0]['options'][0].pop('contact_step')
        with self.assertRaisesRegex(ValueError,'lacks exact'):prefix_actions(r[:4])
        r[0]['options'][0]['action']['t']=35*.01
        self.assertEqual(prefix_actions(r[:4])[2]['body']['t'],35*.01)

    def test_incomplete_effect_and_unsupported_bundle_fail_closed(self):
        r=rows()
        with self.assertRaisesRegex(ValueError,'completed effect'):prefix_actions(r[:3])
        r[0]['options'][0]['kind']='armready_bundle'
        with self.assertRaisesRegex(ValueError,'Unsupported'):prefix_actions(r[:4])

    def test_serve_bundle_uses_real_effect_clock_and_order(self):
        r=rows();action=r[0]['options'][0]['action'];action['t']=70*.01
        toss={'type':'toss','pos':[0,-1.7,.4],'height':.2}
        r[0]['options']=[{'kind':'serve_bundle','actions':[
            {'after_steps':0,'action':action},{'after_steps':10,'action':toss}]}]
        r=r[:4]+[{'ev':'cmd','k':34,'seat':'A','cmd':{'type':'toss'}},
                   {'ev':'effect','k':34,'seq':1,'info':{},'result':{}}]
        actions=prefix_actions(r)
        self.assertEqual(actions[2]['body']['t'],70*.01)
        self.assertEqual(actions[4]['body'],toss) # native planner may delay chunk dispatch
        r[4]['k']=29;r[5]['k']=29
        with self.assertRaisesRegex(ValueError,'before scheduled'):prefix_actions(r)

    def replay(self,mutate=None):
        r=rows();prefix,target=prefix_before(r,2);m=FakeMatch();applied=[]
        low=copy.deepcopy(r[2]['cmd']);info=copy.deepcopy(r[3]['info'])
        if mutate:mutate(low,info)
        layer=SimpleNamespace(lower=lambda *a:(low,info))
        ep=SimpleNamespace(write=lambda *a,**k:None)
        parser=lambda layer,seat,body,m,extra:body
        with patch('rally_fork.verify_public_observation',return_value='png') as verify:
            count=replay_high_prefix(Path('/unused'),m,layer,prefix,target,None,ep,parser,applied)
        return m,applied,count,verify.call_count

    def test_real_lower_apply_and_restore_only_effected_feedback(self):
        m,applied,count,checks=self.replay()
        self.assertEqual((m.k,count,checks),(25,2,2))
        self.assertEqual(len(m.applies),1)
        self.assertEqual((applied[0]['point'],applied[0]['step'],applied[0]['seq']),(3,20,1))
        self.assertEqual(applied[0]['action']['t'],70*.01)
        self.assertEqual(applied[0]['execution_feedback'],{'T_from_now':.7})

    def test_public_command_and_png_are_required(self):
        state={'q':[0], 'point':3,'score':{},'heard':[], 'ball_state':'coming to you',
               'command':{'phase':'approach'},'base_rest':[0,-1.75]}
        m=SimpleNamespace(k=25,dt=.01,observe=lambda seat:copy.deepcopy(state))
        views=SimpleNamespace(view=lambda *a:{'observation':{'image_png_b64':base64.b64encode(b'camera').decode()}})
        row={'seq':2,'image_sha256':hashlib.sha256(b'camera').hexdigest()}
        recorded={'state':copy.deepcopy(state)}
        with patch('rally_fork.public_view',return_value=recorded):
            verify_public_observation(None,row,m,views)
            recorded['state']['command']='none'
            with self.assertRaisesRegex(ValueError,'command'):verify_public_observation(None,row,m,views)
            recorded['state']['command']=state['command'];row['image_sha256']='bad'
            with self.assertRaisesRegex(ValueError,'camera'):verify_public_observation(None,row,m,views)

    def test_mismatch_stops_before_install(self):
        with self.assertRaisesRegex(ValueError,'low command mismatch'):
            self.replay(lambda low,info:low.update(q=[[2]]))
        with self.assertRaisesRegex(ValueError,'planner feedback mismatch'):
            self.replay(lambda low,info:info.update(T_from_now=.6))

if __name__=='__main__':unittest.main()
