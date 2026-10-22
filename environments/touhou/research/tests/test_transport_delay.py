import json
from pathlib import Path
import tempfile
import unittest

from research.transport_delay import build_profile, quantile, sha, transport


class RankMappingTests(unittest.TestCase):
    def test_midrank_ties_and_monotone_inverse(self):
        mapped,probability=transport(1,[1,1,2],[10,20,30])
        self.assertAlmostEqual(probability,1/3)
        self.assertAlmostEqual(mapped,10+20/3)
        values=[transport(value,[1,2,3,4],[10,20,40])[0] for value in (1,2,3,4)]
        self.assertEqual(values,sorted(values))
        self.assertEqual(len(set(values)),4)
        self.assertEqual(quantile([10,20],0),10)
        self.assertEqual(quantile([10,20],1),20)

    def test_singleton_is_constant_not_tail_estimate(self):
        self.assertEqual(transport(1,[1,2],[3.1])[0],3.1)
        self.assertEqual(transport(2,[1,2],[3.1])[0],3.1)

    def test_invalid_samples_and_unmatched_candidate_rejected(self):
        for values,p in (([],.5),([1],-1),([1],1.1),([float('nan')],.5),([1],float('inf'))):
            with self.assertRaises(ValueError):quantile(values,p)
        with self.assertRaises(ValueError):transport(1.5,[1,2],[3,4])
        with self.assertRaises(ValueError):transport(True,[1,2],[3,4])


class SourceAlignmentTests(unittest.TestCase):
    def fixture(self,root):
        episode=root/'episode';episode.mkdir()
        rows=[];vectors=[]
        for index,n in enumerate((1,2,3)):
            net=[1+n*.1,2+n*.1];ready=[net[0]+.5,net[1]+.7];vectors.append(ready)
            for slot in range(2):
                rows.append({'cohort_id':index,'fanout_index':slot,'image_frames':list(range(n)),
                             'capture_clock':{'wall_ms':0},'completed_wall_s':ready[slot],'meta':{'total_s':net[slot]}})
        source=episode/'decisions.jsonl';source.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        profile={'k':2,'joint_delay_vectors_s':vectors,'image_counts':[1,2,3],'apply_overhead_s':.02,
                 'provenance':[{'episode':str(episode),'source_sha256':{'decisions.jsonl':sha(source)},
                                'excluded_terminal_cohorts':[],'complete_cohorts':3,'clock_offset_s':0}]}
        joint=root/'joint.json';joint.write_text(json.dumps(profile))
        serial=root/'serial.jsonl';serial.write_text(''.join(json.dumps({'meta':{'valid':True,'total_s':3+n*.1,'shape':{
            'images':['image']*n,'model':'gpt-6.1-sol','tier':'ultrafast','effort':'low','max_output_tokens':512,'detail':'high','schema_sha256':'fixture'}}})+'\n' for n in (1,2,3)))
        return joint,serial,source

    def test_verified_sources_preserve_residuals_and_label_modeled_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);joint,serial,source=self.fixture(root)
            result=build_profile(joint,serial,expected_serial=3,expected_joint=3)
            self.assertEqual(result['kind'],'modeled_marginal_transport')
            self.assertTrue(result['not_observed_concurrent_profile'])
            self.assertEqual(result['singleton_constant_image_counts'],[1,2,3])
            self.assertAlmostEqual(result['transport_audit'][0]['preserved_non_network_s'][0],.5)
            self.assertAlmostEqual(result['joint_delay_vectors_s'][0][0],3.6)
            rows=[json.loads(line) for line in serial.read_text().splitlines()]
            for row in rows:
                shape=row['meta']['shape'];shape['image_count']=len(shape.pop('images'))
            serial.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            self.assertEqual(build_profile(joint,serial,expected_serial=3,expected_joint=3),result)

    def test_source_hash_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            joint,serial,source=self.fixture(Path(temp));source.write_text(source.read_text()+'\n')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                build_profile(joint,serial,expected_serial=3,expected_joint=3)

    def test_negative_residual_rejected_even_after_hash_and_vector_alignment(self):
        with tempfile.TemporaryDirectory() as temp:
            joint,serial,source=self.fixture(Path(temp));data=json.loads(joint.read_text());rows=[json.loads(s) for s in source.read_text().splitlines()]
            rows[0]['meta']['total_s']=rows[0]['completed_wall_s']+.01
            source.write_text(''.join(json.dumps(row)+'\n' for row in rows));data['provenance'][0]['source_sha256']['decisions.jsonl']=sha(source);joint.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Negative historical'):
                build_profile(joint,serial,expected_serial=3,expected_joint=3)

    def test_vector_alignment_and_expected_counts_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            joint,serial,source=self.fixture(Path(temp))
            with self.assertRaisesRegex(ValueError,'serial sample count'):build_profile(joint,serial,expected_serial=4,expected_joint=3)
            data=json.loads(joint.read_text());data['joint_delay_vectors_s'][0][0]+=.1;joint.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'alignment mismatch'):build_profile(joint,serial,expected_serial=3,expected_joint=3)


if __name__=='__main__':unittest.main()
