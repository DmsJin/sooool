import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from research.demo_prior_learning import prepare,learning_schema

class DemoPriorTest(unittest.TestCase):
    def test_original_images_past_controls_and_only_six_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'human';source.mkdir()
            (source/'verification.json').write_text(json.dumps({'verified':True,'bounded_float':True}))
            (source/'manifest.json').write_text(json.dumps({'provider':'human'}))
            frames=[];actions=[]
            for i in range(1,17):
                data=b'original'+bytes([i]);name=f'{i}.png';(source/name).write_bytes(data)
                frames.append({'frame':i*120,'held':[0,1,1,0],'clock':{'visual_frame':i*120+165,'intro':0},'png':name,'sha256':hashlib.sha256(data).hexdigest(),'HIDDEN_STATE':{'x':999}})
                actions.append({'logical_frame':i*120,'visual_frame':i*120+165,'action':[0,1,1,0],'HIDDEN_STATE':{'x':999}})
            actions.append({'logical_frame':3000,'visual_frame':3165,'action':[7,1,1,1]})
            (source/'frames.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in frames))
            (source/'actions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in actions))
            output=root/'bundle';bundle=prepare(source,output)
            self.assertEqual(len(bundle['batches']),6)
            self.assertEqual(sum(len(b['images']) for b in bundle['batches']),16)
            self.assertNotIn('HIDDEN_STATE',json.dumps(bundle))
            for batch in bundle['batches']:
                last=batch['images'][-1]['visual_frame']
                self.assertTrue(all(a['visual_frame']<=last for a in batch['past_completed_demonstration_controls']))
                for image in batch['images']:self.assertEqual((output/image['png']).read_bytes(),(source/image['source_png']).read_bytes())
            self.assertNotIn('3000',json.dumps(bundle))

    def test_schema_is_provisional_analysis_not_action_script(self):
        schema=learning_schema();self.assertFalse(schema['additionalProperties'])
        self.assertNotIn('plan',schema['properties'])
        self.assertEqual(schema['properties']['policy_hypotheses']['maxItems'],4)
        self.assertEqual(schema['properties']['boss_estimates']['maxItems'],3)

if __name__=='__main__':unittest.main()
