"""Evidence boundaries for missing canceled inputs; no native/model/API."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from partial_evidence import digest,resolve,snapshot_bytes


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.source=Path(self.tmp.name)
        (self.source/'observations').mkdir();self.directory=self.source/'decision_00021';self.directory.mkdir()
        self.state={'q':[1,2,3],'point':5};self.text='policy\nSTATE '+json.dumps(self.state)+'\nIMAGE_META {}'
        self.row={'seq':21,'k':100,'image_sha256':'png'}
        self.cancel=[{'ev':'act_dropped','seq':21,'why':'screen_unused_tail_cancel'}]
    def tearDown(self):self.tmp.cleanup()
    def input(self,text=None):
        (self.directory/'input.json').write_text(json.dumps({'params':{'input':[{'text':text or self.text}]}}))
    def parent(self):
        raw=snapshot_bytes(21,100,self.state,'png',self.text)
        (self.source/'observations/00021.json').write_bytes(raw)
        self.row.update(parent_observation_sha256=digest(raw),prompt_sha256=digest(self.text.encode()))
    def test_legacy_canceled_unsent_has_no_q_and_is_not_actual_sent(self):
        proof=resolve(self.source,self.row,self.cancel)
        self.assertIsNone(proof['state']);self.assertTrue(proof['q_unrecorded_canceled'])
        self.assertTrue(proof['canceled_unsent']);self.assertFalse(proof['worker_input_recorded'])
    def test_missing_input_used_by_effect_or_visible_is_rejected(self):
        for ev in ('effect','model_visible'):
            with self.assertRaisesRegex(ValueError,'not a documented'):
                resolve(self.source,self.row,self.cancel+[{'ev':ev,'seq':21}])
    def test_missing_input_not_canceled_is_rejected_even_with_parent(self):
        self.parent()
        with self.assertRaisesRegex(ValueError,'not a documented'):resolve(self.source,self.row,[])
    def test_missing_input_with_result_is_rejected(self):
        (self.directory/'result.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'not a documented'):resolve(self.source,self.row,self.cancel)
    def test_parent_canceled_keeps_original_q_but_not_actual_sent(self):
        self.parent();proof=resolve(self.source,self.row,self.cancel)
        self.assertEqual(proof['state'],self.state);self.assertFalse(proof['q_unrecorded_canceled'])
        self.assertFalse(proof['worker_input_recorded']);self.assertTrue(proof['parent_recorded'])
    def test_parent_tamper_rejected(self):
        self.parent();path=self.source/'observations/00021.json';record=json.loads(path.read_text());record['state']['q'][0]=99
        path.write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError,'seal mismatch'):resolve(self.source,self.row,self.cancel)
    def test_worker_prompt_and_state_must_match_parent(self):
        self.parent();self.input(self.text+' tamper')
        with self.assertRaisesRegex(ValueError,'prompt differs'):resolve(self.source,self.row,[])
        self.input();self.assertEqual(resolve(self.source,self.row,[])['state'],self.state)
        self.state['q'][0]=99;self.parent() # internally sealed parent still disagrees with actual recorded input
        with self.assertRaisesRegex(ValueError,'STATE differs'):resolve(self.source,self.row,[])
    def test_legacy_recorded_worker_input_remains_strictly_checkable(self):
        self.input();proof=resolve(self.source,self.row,[{'ev':'effect','seq':21}])
        self.assertTrue(proof['worker_input_recorded']);self.assertFalse(proof['canceled_unsent'])
        self.assertEqual(proof['state'],self.state)

if __name__=='__main__':unittest.main()
