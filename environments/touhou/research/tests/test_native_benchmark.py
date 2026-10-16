import json
from pathlib import Path
import tempfile
import unittest
from collections import Counter
from research.native_benchmark import make_blocks,summarize,digest,validate_response,score_grounding

class BenchmarkTest(unittest.TestCase):
    def test_same_frozen_inputs_balanced_randomized_arms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);cases=[]
            for i in range(8):
                folder=root/str(i);folder.mkdir();image=folder/'image.png';image.write_bytes(b'original png'+bytes([i]))
                public=folder/'input.json';public.write_text(json.dumps({'config':{'speed':1},'observation':{'image_frames':[i],'held':[0,1,1,0]},'profile':{'p50_s':2,'p95_s':3}}))
                cases.append({'id':str(i),'input_file':str(public.relative_to(root)),'input_sha256':digest(public.read_bytes()),'images':[{'file':str(image.relative_to(root)),'sha256':digest(image.read_bytes()),'frame':i}], 'private_labels':'DO_NOT_READ.json'})
            (root/'manifest.json').write_text(json.dumps({'cases':cases}))
            blocks,schema=make_blocks(root)
            self.assertEqual(len(blocks),24)
            for block in blocks:self.assertEqual(set(block['order']),{'default','lean','aggressive'})
            for position in range(3):self.assertEqual(Counter(b['order'][position] for b in blocks),{'default':8,'lean':8,'aggressive':8})
            self.assertEqual(blocks,make_blocks(root)[0])
            by_case={}
            for block in blocks:by_case.setdefault(block['case_id'],set()).add(block['prompt_sha256'])
            self.assertTrue(all(len(hashes)==1 for hashes in by_case.values()))

    def test_failures_retained_and_paired_population_explicit(self):
        def row(arm,seconds,block=0):return {'arm':arm,'block_id':block,'position':0,'valid_contract':True,'complete_return_s':seconds,'response':{'meta':{'token_usage':{'total':{'inputTokens':100,'cachedInputTokens':60,'outputTokens':20,'reasoningOutputTokens':10}}}}}
        report=summarize([row('default',10),row('lean',7),row('aggressive',5),{'arm':'aggressive','block_id':1,'position':0,'response':None}])
        self.assertEqual(report['arms']['aggressive']['failures'],1)
        self.assertEqual(report['paired_complete_return_differences_s']['aggressive-default']['p50'],-5)
        self.assertEqual(report['arms']['lean']['uncachedInputTokens']['p50'],40)

    def test_private_coordinates_only_posthoc_and_null_counts_separate(self):
        answer={'player':[203,404],'boss':[250,90],'aim_x':240,'plan':[{'move':0,'shoot':1,'focus':1,'bomb':0,'duration':12}]}
        rows=[{'arm':'default','case_id':'one','response':{'answer':json.dumps(answer)}}]
        truth={'observed_ground_truth':{'one':{'player_present':True,'player':{'x':200,'y':400},'boss':{'x':250,'y':90}}}}
        result=score_grounding(rows,truth)['private_posthoc_coordinate_audit']['default']
        self.assertEqual(result['player_error_px']['p50'],5)
        self.assertEqual(result['boss_error_px']['p50'],0)
        answer['player']=None;rows[0]['response']['answer']=json.dumps(answer)
        result=score_grounding(rows,truth)['private_posthoc_coordinate_audit']['default']
        self.assertEqual(result['present_player_reported_null'],1)
        self.assertEqual(result['player_error_px']['n'],0)

    def test_contract_validation_does_not_claim_accuracy(self):
        good={'player':[200,400],'boss':[250,90],'aim_x':240,'plan':[{'move':7,'shoot':1,'focus':1,'bomb':0,'duration':12}]}
        self.assertEqual(validate_response(good),good)
        bad=dict(good,player=[float('nan'),400])
        with self.assertRaises(ValueError):validate_response(bad)

if __name__=='__main__':unittest.main()
