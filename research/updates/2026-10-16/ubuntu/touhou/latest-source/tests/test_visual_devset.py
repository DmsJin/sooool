import unittest
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from research.visual_devset import build,review,digest
from research.visual_devset import public_metadata,metrics
from research.visual_devset import candidate_efforts,compare,main

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

    def test_effort_map_validated_before_output_creation(self):
        self.assertEqual(candidate_efforts(['a','b']),{'a':'low','b':'low'})
        self.assertEqual(candidate_efforts(['a','b'],'low',{'b':'medium'}),{'a':'low','b':'medium'})
        with tempfile.TemporaryDirectory() as temp:
            for index,overrides in enumerate(({'unselected':'medium'},{'a':'high'},[],{'a':None})):
                output=Path(temp)/str(index)
                with self.assertRaises(ValueError):
                    compare(Path(temp)/'missing-dataset',output,Path(temp),['a'],effort_by_candidate=overrides)
                self.assertFalse(output.exists())

    def test_mixed_effort_cache_and_per_answer_actual_metadata(self):
        clients=[];seen=[]
        class Client:
            def __init__(self,suite,output,schema,**options):
                self.effort=options['effort'];clients.append(self)
            def act(self,prompt,images,directory):
                seen.append((prompt,self.effort,images))
                return {'answer':'[[0,1,1,0,1]]','meta':{'effort':self.effort,'native_reasoning_effort':self.effort}}
            def close(self):pass
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);dataset=root/'dataset';dataset.mkdir();image=b'\x89PNG\r\n\x1a\noriginal'
            (dataset/'image.png').write_bytes(image);public={'observation':{},'config':{},'profile':{}}
            (dataset/'input.json').write_text(json.dumps(public))
            (dataset/'manifest.json').write_text(json.dumps({'cases':[{'id':'case','input_file':'input.json',
                'input_sha256':digest((dataset/'input.json').read_bytes()),'images':[{'file':'image.png','sha256':digest(image)}]}]}))
            candidates=['tracking_dodge_safe_intercept_v2','tracking_dodge_visual_v5']
            with patch('research.subscription.SubscriptionClient',Client),patch('research.policies.make_prompt',return_value='identical frozen task'),patch('research.visual_devset.review'):
                records=compare(dataset,root/'output',root,candidates,repeats=2,workers=1,
                                effort_by_candidate={candidates[1]:'medium'})
            self.assertEqual(len(clients),2)  # Same schema, separate effort processes.
            self.assertEqual({client.effort for client in clients},{'low','medium'})
            self.assertTrue(all(prompt=='identical frozen task' and imgs==[image]for prompt,_,imgs in seen))
            self.assertTrue(all(r['effort']==r['requested_effort']==r['response']['meta']['native_reasoning_effort']for r in records))
            results=json.loads((root/'output/results.json').read_text())
            self.assertEqual(results['effort'],'mixed')
            self.assertEqual(results['effort_by_candidate'],{candidates[0]:'low',candidates[1]:'medium'})

    def test_compare_cli_defaults_low_and_accepts_medium_override_map(self):
        base=['visual_devset','compare','--dataset','/dataset','--output','/output','--suite','/suite','--candidates','a']
        with patch('sys.argv',base),patch('research.visual_devset.compare') as call:
            main();self.assertEqual(call.call_args.args[-2: ],('low',None))
        with patch('sys.argv',base+['--effort','medium','--effort-by-candidate','{"a":"low"}']),patch('research.visual_devset.compare') as call:
            main();self.assertEqual(call.call_args.args[-2: ],('medium',{'a':'low'}))

if __name__=='__main__':unittest.main()
