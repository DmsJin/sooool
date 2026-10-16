import unittest
import json
from pathlib import Path
import tempfile
from research.visual_devset import build,review,digest
from research.visual_devset import public_metadata,metrics

class VisualDevsetTest(unittest.TestCase):
    def test_private_and_sampled_delay_excluded(self):
        row={'image_frames':[1,2,3],'held':[0,1,1,0],'capture_clock':{'frame':3,'intro':0,'player':{'x':999}},
             'state':{'boss':{'x':123}},'plan':[[3,1,1,0,48]],'delay_frames':133,'private_labels':{'answer':'LEFT'}}
        public=public_metadata(row,{'speed':1},{'p50_s':2,'control_age_p95_s':3,'joint_delay_vectors_s':[[4]]})
        text=str(public)
        for secret in ('999','123','133','LEFT','joint_delay_vectors'):self.assertNotIn(secret,text)
        self.assertEqual(public['observation']['held'],[0,1,1,0])

    def test_manifest_hashes_unchanged_images_and_private_separation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);episode=root/'episode';source=episode/'decision_00000';source.mkdir(parents=True)
            image=b'\x89PNG\r\n\x1a\noriginal-unchanged'
            (source/'image_0.png').write_bytes(image)
            profile=root/'profile.json';profile.write_text(json.dumps({'p50_s':2,'control_age_p95_s':3}))
            (episode/'config.json').write_text(json.dumps({'profile':str(profile),'speed':1}))
            row={'seq':0,'image_frames':[40],'logical_frame':40,'visual_frame':42,'image_sha256':[digest(image)],'held':[0,1,1,0]}
            (episode/'issued.jsonl').write_text(json.dumps(row)+'\n')
            (episode/'decisions.jsonl').write_text(json.dumps({'seq':0,'plan':[[7,1,1,0,12]]})+'\n')
            (source/'prompt.txt').write_text('Known returned plan: {"action":[0,1,1,0],"end":40}.\n')
            dataset=root/'dataset'
            manifest=build(root,[{'id':'safe-case','episode':'episode','seq':0,'rubric':['SECRET_RUBRIC']}],dataset)
            case=manifest['cases'][0]
            self.assertEqual((dataset/case['images'][0]['file']).read_bytes(),image)
            public=(dataset/case['input_file']).read_text()
            self.assertNotIn('SECRET_RUBRIC',public)
            self.assertNotIn('source_executed',public)
            self.assertEqual(json.loads(public)['known_plan']['end'],40)
            review(dataset,dataset)
            self.assertTrue((dataset/'review.html').exists())
            (dataset/case['private_labels']).unlink()
            review(dataset,dataset)
            self.assertIn('Private labels remain', (dataset/'review.html').read_text())

    def test_metrics_are_descriptive_not_gold_action(self):
        for action in ('[[0,1,1,0,20]]','[[3,1,1,0,8]]','[[7,1,0,1,48]]'):
            self.assertTrue(metrics(action)['valid_contract'])
        self.assertTrue(metrics('[[3,1,1,0,8]]')['focused_small_nudge'])
        self.assertFalse(metrics('[[3,1,1,0,80]]')['valid_contract'])
        self.assertNotIn('correct',metrics('[[0,1,1,0,20]]'))

if __name__=='__main__':unittest.main()
