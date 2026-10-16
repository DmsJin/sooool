import json
from pathlib import Path
import tempfile
import unittest

from research.early_control_delays import calibrate_early
from research.early_transport_delay import build_early_transport
from research.tests import test_early_control_delays as early_fixture


class EarlyTransportDelayTest(unittest.TestCase):
    def fixture(self,root):
        root=Path(root);episode=root/'episode';episode.mkdir()
        early_fixture.EarlyControlDelaysTest().fixture(episode)
        rows=[json.loads(x) for x in (episode/'decisions.jsonl').read_text().splitlines()]
        for row in rows:
            c=row['cohort_id'];i=row['fanout_index']
            row['meta']['shape']=dict(model='gpt-6.1-sol',tier='ultrafast',effort='low',max_output_tokens=512,detail='high',schema_sha256='fixture-schema',images=['hash']*len(row['image_frames']))
            row['meta']['stage_timing']['network_started_wall_s']=10+c+.2
            path=episode/f"decision_{row['seq']:05d}"/'early_result.json'
            early=json.loads(path.read_text());early['meta']['legal_action_s']=.8+i*.2;path.write_text(json.dumps(early))
        (episode/'decisions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
        joint=root/'joint.json';joint.write_text(json.dumps(calibrate_early([episode],k=2,terminal_tail_policy='durable_plus_median_poll_lag')))
        serial=root/'serial.jsonl'
        serial.write_text(''.join(json.dumps({'meta':{'valid':True,'legal_action_s':value,'shape':{**rows[0]['meta']['shape'],'images':['serial-hash']*n}}})+'\n' for n,value in ((1,2),(3,2),(3,4))))
        return joint,serial,episode

    def test_verified_mapping_preserves_launch_publication_and_paired_terminal(self):
        with tempfile.TemporaryDirectory() as root:
            joint,serial,episode=self.fixture(root)
            output=build_early_transport(joint,serial,expected_serial=3)
            self.assertEqual(output['kind'],'modeled_early_prompt_transport')
            self.assertEqual(output['control_age_kind'],'modeled_early_prompt_transport')
            self.assertTrue(output['not_observed_concurrent_profile'])
            self.assertEqual(output['singleton_constant_image_counts'],[1])
            self.assertEqual(output['marginal_sample_counts']['past_real'],{'1':2,'3':2})
            audit=output['transport_audit'][0]['slots'][0]
            self.assertAlmostEqual(audit['capture_to_network_s'],.2)
            self.assertAlmostEqual(audit['publication_residual_s'],.1)
            self.assertAlmostEqual(audit['terminal_ready_tail_s'],.4)
            self.assertAlmostEqual(output['joint_delay_vectors_s'][0][0],2.3)
            for ready,terminal in zip(output['joint_delay_vectors_s'],output['joint_terminal_delay_vectors_s']):
                for r,t in zip(ready,terminal):self.assertAlmostEqual(t-r,.4)
            self.assertLess(output['joint_delay_vectors_s'][1][0],output['joint_delay_vectors_s'][1][1])

    def test_hash_and_vector_mismatch_fail_closed(self):
        for kind in ('source','early','vector','terminal'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root:
                joint,serial,episode=self.fixture(root)
                if kind=='source':(episode/'issued.jsonl').write_text((episode/'issued.jsonl').read_text()+'\n')
                elif kind=='early':
                    p=episode/'decision_00000/early_result.json';p.write_text(p.read_text()+'\n')
                else:
                    profile=json.loads(joint.read_text());field='joint_delay_vectors_s' if kind=='vector' else 'joint_terminal_delay_vectors_s'
                    profile[field][0][0]+=.1;joint.write_text(json.dumps(profile))
                with self.assertRaisesRegex(ValueError,'hash mismatch|alignment mismatch'):
                    build_early_transport(joint,serial,expected_serial=3)

    def test_strict_serial_identity_and_shape(self):
        for damage in ('schema','model','cap','effort','missing_stratum','invalid','negative','missing_metric'):
            with self.subTest(damage=damage),tempfile.TemporaryDirectory() as root:
                joint,serial,episode=self.fixture(root)
                rows=[json.loads(x) for x in serial.read_text().splitlines()]
                if damage in ('schema','model','cap','effort'):
                    field={'schema':'schema_sha256','cap':'max_output_tokens'}.get(damage,damage)
                    rows[0]['meta']['shape'][field]=256 if damage=='cap' else 'mismatch'
                if damage=='missing_stratum':rows[0]['meta']['shape']['images']=['hash']*3
                if damage=='invalid':rows[0]['meta']['valid']=False
                if damage=='negative':rows[0]['meta']['legal_action_s']=-1
                if damage=='missing_metric':del rows[0]['meta']['legal_action_s']
                serial.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaises((ValueError,KeyError)):
                    build_early_transport(joint,serial,expected_serial=3)

    def test_explicit_count_and_source_override(self):
        with tempfile.TemporaryDirectory() as root:
            joint,serial,episode=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'expected_serial'):build_early_transport(joint,serial)
            with self.assertRaisesRegex(ValueError,'sample count'):build_early_transport(joint,serial,expected_serial=4)
            output=build_early_transport(joint,serial,[episode],3)
            self.assertEqual(len(output['joint_delay_vectors_s']),2)
            with self.assertRaisesRegex(ValueError,'Unused'):build_early_transport(joint,serial,[Path(root)/'other'],3)

if __name__=='__main__':unittest.main()
