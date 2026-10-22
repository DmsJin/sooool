import json
from pathlib import Path
import tempfile
import unittest
from runtime.cli import ROOT
from runtime.touhou_records import evaluation_record

class EvaluationRecords(unittest.TestCase):
    def make(self,root,mode='realtime_api',status='won',terminal=True):
        out=root/'run';out.mkdir();ep=out/'episode';ep.mkdir()
        (out/'manifest.json').write_text(json.dumps({'mode':mode,'recipe':{'args':{'seed':1,'decision_fanout':4}}}))
        (ep/'summary.json').write_text(json.dumps({'seed':1,'complete':True,'won':status=='won','status':status,'terminal_accounting_complete':terminal,'calls':8}))
        clock={'mode':'realtime','speed':1,'paused':False,'blur_events':0}
        (ep/'final_state.json').write_text(json.dumps({'clock':clock}))
        (ep/'actions.jsonl').write_text('\n'.join(json.dumps({'capture_to_apply_s':d,'apply_clock':clock}) for d in [2,3]))
        return out
    def test_simulated_win_is_not_realtime_acceptance(self):
        with tempfile.TemporaryDirectory() as d:
            out=self.make(Path(d),'subscription_with_simulated_profile')
            r=evaluation_record(ROOT,out)
            self.assertTrue(r['won']);self.assertFalse(r['passed']);self.assertIsNone(r['latency'])
    def test_api_requires_terminal_accounting_and_defeat(self):
        for status,terminal,passed in [('won',True,True),('won',False,False),('survived',True,False)]:
            with self.subTest(status=status,terminal=terminal),tempfile.TemporaryDirectory() as d:
                r=evaluation_record(ROOT,self.make(Path(d),status=status,terminal=terminal))
                self.assertEqual(r['passed'],passed);self.assertEqual(r['latency']['median_s'],2.5)
    def test_paused_or_slow_game_cannot_pass_as_realtime(self):
        for changed in ({'paused':True},{'speed':0.5},{'blur_events':1}):
            with tempfile.TemporaryDirectory() as d:
                out=self.make(Path(d));p=out/'episode/final_state.json';f=json.loads(p.read_text());f['clock'].update(changed);p.write_text(json.dumps(f))
                self.assertFalse(evaluation_record(ROOT,out)['passed'])
