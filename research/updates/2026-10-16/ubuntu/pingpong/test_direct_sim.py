"""Pure controller fixtures: no native world, subprocess, model or API."""
import base64
import concurrent.futures as cf
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import simulate
import verify_replay


class DirectSimTests(unittest.TestCase):
    def test_direct_selects_only_new_io_and_preserves_legacy(self):
        module=SimpleNamespace(prompt=object(),parse=object())
        with patch.dict(sys.modules,{'direct_io':module,'candidates':None,'builtin_players':None}):
            self.assertEqual(simulate.io_for_variant('direct_high'),(module.prompt,module.parse))
            self.assertEqual(simulate.io_for_variant('baseline'),(simulate.prompt,simulate.parse))

    def test_direct_delivery_rechecks_phase_point_and_sequence(self):
        req={'seq':4,'point':7}
        self.assertIsNone(simulate.direct_drop_reason(req,7,'playing',3))
        self.assertEqual(simulate.direct_drop_reason(req,8,'playing',3),'point_changed')
        self.assertEqual(simulate.direct_drop_reason(req,7,'unit_over',3),'point_over')
        self.assertEqual(simulate.direct_drop_reason(req,7,'playing',4),'stale_sequence')
        self.assertEqual(simulate.direct_drop_reason(req,7,'playing',5),'stale_sequence')

    def test_direct_replay_never_skips_missing_state(self):
        with self.assertRaisesRegex(ValueError,'missing public STATE'):
            verify_replay.recorded_state('DIRECT without state',True)
        self.assertIsNone(verify_replay.recorded_state('legacy without state'))
        state={'q':[0.]*9,'point':1,'score':{},'heard':[],'ball_state':'your serve'}
        text='DIRECT\nSTATE '+json.dumps(state)+'\nIMAGE_META {}'
        self.assertEqual(verify_replay.recorded_state(text,True),state)

    def test_screened_replay_requires_opt_in_and_cannot_create_full_replay_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp);state={'q':[0.]*9,'point':1,'score':{},'heard':[],'ball_state':'your serve'}
            text='DIRECT\nSTATE '+json.dumps(state)+'\nIMAGE_META {}';png=b'public fixture'
            (source/'summary.json').write_text(json.dumps({'finished':False,'screened':True,'failure':None,
                'variant':'direct_v1','k':1,'calls':1,'digest':'fixture'}))
            (source/'episode.jsonl').write_text(json.dumps({'ev':'header','cfg':{
                'sport':'tabletennis','format':'match','seats':['A'],'seed':7}})+'\n'+json.dumps({
                'ev':'model_issued','k':0,'seq':0,'image_sha256':simulate.hashlib.sha256(png).hexdigest()}))
            (source/'decision_00000').mkdir();(source/'observations').mkdir()
            (source/'decision_00000/input.json').write_text(json.dumps({'params':{'input':[{'text':text}]}}))
            (source/'observations/00000.prompt.txt').write_text(text)
            class Match:
                k=0;dt=.01
                def observe(self,seat):return state
                def step(self):self.k+=1
                def state_digest(self):return 'fixture'
                def scores(self):return {'A':0,'opponent':0}
            class Views:
                def __init__(self,*args):pass
                def view(self,*args):return {'observation':{'image_png_b64':base64.b64encode(png).decode()}}
            sport=SimpleNamespace(build=lambda cfg:Match(),worker_call=lambda:None)
            with patch.object(verify_replay,'load_plugin',return_value=sport) as build, \
                 patch.object(verify_replay,'Views',Views),patch.object(verify_replay.spec_mod,'load',return_value={}):
                with self.assertRaises(AssertionError):verify_replay.run(source,True)
                build.assert_not_called()
                verify_replay.run(source,True,allow_screened=True)
            self.assertFalse((source/'verified_replay.json').exists())
            report=json.loads((source/'verified_screened_replay.json').read_text())
            self.assertTrue(report['partial_screened']);self.assertFalse(report['acceptance'])
            self.assertEqual((report['observations_verified'],report['camera_pngs_verified']),(1,1))

    def run_fixture(self,parser,answers,lower_error=None):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);root=Path(temp.name)
        profile=root/'profile.json';profile.write_text(json.dumps({'delays_s':[0.],'p50_s':0.,'p95_s':0.}))
        calls=[];effects=[];events=[]
        class Match:
            k=0;dt=.01
            def phase(self):return SimpleNamespace(state='finished' if self.k>=4 else 'playing')
            def observe(self,seat):return {'step':self.k,'point':1,'q':[0.]*9,'score':{'you':0,'opponent':0},'heard':[],'ball_state':'your serve'}
            def step(self):self.k+=1;return []
            def apply(self,seat,body):effects.append(body);return {'command':'traj'}
            def scores(self):return {'A':0,'opponent':0}
            def state_digest(self):return 'fixture'
        match=Match()
        class Layer:
            def lower(self,seat,body,unused,m):
                if lower_error:raise lower_error
                return body,{'fixture':True}
        layer=Layer();sport=SimpleNamespace(build=lambda cfg:match,action_layer=lambda level:layer,
                                           worker_call=lambda:None)
        class Views:
            def __init__(self,*args):pass
            def view(self,seat,header):return {'state':match.observe(seat),'observation':{'image_png_b64':base64.b64encode(b'public image fixture').decode(),'view_steps':[match.k]}}
        class Episode:
            def __init__(self,path):pass
            def write(self,ev,**data):events.append({'ev':ev,**data})
        class Pool:
            def __init__(self,*args,**kw):pass
            def submit(self,text,image,directory):
                calls.append(text);future=cf.Future();future.set_result({'answer':answers[min(len(calls)-1,len(answers)-1)]});return future
            def close(self,**kw):pass
        spec={'cameras':[],'raw_public_spec':'unchanged'}
        def prompt(view,seen_spec,timing,variant):
            self.assertEqual(seen_spec,spec)
            self.assertNotIn('stance_check',view['state'])
            return 'DIRECT\nSPEC '+json.dumps(seen_spec)+'\nSTATE '+json.dumps(view['state'])+'\nIMAGE_META '+json.dumps({'view_steps':[match.k]})
        args=SimpleNamespace(variant='direct_high',screen_points=0,screen_decisions=0,screen_shots=0,
            fork_from=None,fork_seq=None,fork_replay_high=False,fork_max_decisions=30,resume_from=None,
            output=root/'episode',profile=profile,seed=7,level=1,slowdown=10,workers=1,stride=1,capacity=3,
            delay_scale=1.,max_steps=4)
        with patch.dict(sys.modules,{'direct_io':SimpleNamespace(prompt=prompt,parse=parser),
                                      'candidates':None,'builtin_players':None}), \
             patch.object(simulate,'load_plugin',return_value=sport),patch.object(simulate,'Views',Views), \
             patch.object(simulate,'Episode',Episode),patch.object(simulate,'Pool',Pool), \
             patch.object(simulate,'_header'),patch.object(simulate,'seat_spec',return_value=spec), \
             patch.object(simulate.spec_mod,'load',return_value={}), \
             patch.object(simulate.score_mod,'compute',return_value={}), \
             patch.object(simulate,'decide',return_value=SimpleNamespace(winner=None)), \
             patch.object(simulate,'parse_action',side_effect=lambda layer,seat,body,m,ctx:body):
            error=None
            try:simulate.run(args)
            except RuntimeError as exc:error=exc
        return args.output,events,effects,error

    def test_malformed_action_is_logged_and_next_action_still_executes(self):
        def parser(text):
            if text=='bad raw output':raise ValueError('invalid action')
            return json.loads(text)
        output,events,effects,error=self.run_fixture(parser,['bad raw output','{"type":"move","base":[0,-1.7]}'])
        self.assertIsNone(error)
        summary=json.loads((output/'summary.json').read_text());self.assertEqual(summary['refused'],1)
        self.assertTrue(effects)
        refusal=next(e for e in events if e['ev']=='refused');self.assertEqual(refusal['raw_answer'],'bad raw output')
        self.assertTrue(all(e['options'] is None and e['preprocessing_in_delay'] for e in events if e['ev']=='model_issued'))
        self.assertTrue(any(e['ev']=='execution_block' for e in events))
        self.assertTrue((output/'public_spec.json').exists())
        self.assertIn('\nSTATE ',(output/'observations/00000.prompt.txt').read_text())
        self.assertEqual((output/'observations/00000.png').read_bytes(),b'public image fixture')

    def test_technical_parser_and_lower_errors_are_not_model_refusals(self):
        def broken(text):raise RuntimeError('parser implementation failed')
        for parser,lower in ((broken,None),(json.loads,RuntimeError('native lowering failed'))):
            output,events,effects,error=self.run_fixture(parser,['{"type":"move","base":[0,-1.7]}'],lower)
            self.assertIsNotNone(error)
            summary=json.loads((output/'summary.json').read_text());self.assertEqual(summary['refused'],0)
            self.assertIn('failed',summary['failure'])

    def test_native_refused_is_logged_with_raw_action_and_does_not_end_episode(self):
        output,events,effects,error=self.run_fixture(json.loads,['{"type":"act","t":-1}'],
                                                   simulate.Refused('invalid high action'))
        self.assertIsNone(error)
        refusals=[e for e in events if e['ev']=='refused']
        self.assertTrue(refusals)
        self.assertEqual(refusals[0]['action'],{'type':'act','t':-1})
        self.assertEqual(refusals[0]['raw_answer'],'{"type":"act","t":-1}')
        summary=json.loads((output/'summary.json').read_text());self.assertIsNone(summary['failure'])
        self.assertEqual(summary['refused'],len(refusals))


if __name__=='__main__':unittest.main()
