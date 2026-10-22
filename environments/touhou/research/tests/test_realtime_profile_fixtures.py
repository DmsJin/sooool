import json
from pathlib import Path
import struct
import tempfile
import unittest
from research.realtime_profile_fixtures import build_fixtures,digest,JOINT,TERMINAL,STRESS,parse_quotas,remove_sim_appendices
from research.wire_schema import grounded_schema,schema_hash


class RealtimeProfileFixturesTest(unittest.TestCase):
    def fixture(self,root,name='episode',counts=(1,2,3,3),seed=1):
        episode=Path(root)/name;episode.mkdir()
        config=dict(provider='subscription',mode='sim',structured=True,max_duration=48,max_output_tokens=512,chunk_size=1,candidate='new_tracking',seed=seed,cohort_delay='empirical_joint',decision_fanout=4,simulation_terminal_hold=True,latency_scale=1.2)
        (episode/'config.json').write_text(json.dumps(config));(episode/'summary.json').write_text(json.dumps({'complete':True,'won':False}))
        issued=[];decisions=[]
        for cohort,n in enumerate(counts):
            task=f'Full GAME task; obs {seed}:{cohort}; latency historical 2.7s; gating; visualmemory; action format.\n'.encode()
            prompt=task+JOINT.encode()+TERMINAL.encode()+STRESS.format(scale=1.2).encode()
            images=[b'\x89PNG\r\n\x1a\n'+b'\0'*8+struct.pack('>II',640,480)+f'fixture{seed}:{cohort}:{i}'.encode() for i in range(n)]
            for slot in range(4):
                seq=cohort*4+slot;directory=episode/f'decision_{seq:05d}';directory.mkdir()
                (directory/'prompt.txt').write_bytes(prompt)
                for i,data in enumerate(images):(directory/f'image_{i}.png').write_bytes(data)
                row=dict(seq=seq,cohort_id=cohort,fanout_index=slot,decision_fanout=4,visual_frame=cohort*120,image_frames=list(range(n)),prompt_sha256=digest(prompt),image_sha256=[digest(data) for data in images])
                issued.append(row);decisions.append({**row,'meta':{'model':'gpt-6.1-sol','effort':'low','output_schema_sha256':schema_hash(grounded_schema(1,48)),'image_sha256s':row['image_sha256']}})
        for name,rows in [('issued.jsonl',issued),('decisions.jsonl',decisions)]:
            (episode/name).write_text(''.join(json.dumps(row)+'\n' for row in rows))
        return episode

    def test_only_exact_sim_appendices_deleted_with_byte_audit(self):
        config=dict(mode='sim',cohort_delay='empirical_joint',decision_fanout=4,simulation_terminal_hold=True,latency_scale=1.2)
        game='任务原文\nLatency context; output schema; visual memory; winner gating.\n'.encode()
        source=game+JOINT.encode()+TERMINAL.encode()+STRESS.format(scale=1.2).encode()
        result,audit=remove_sim_appendices(source,config)
        self.assertEqual(result,game);self.assertEqual(len(audit),3)
        for row in audit:
            removed=source[row['source_start_byte']:row['source_end_byte']]
            self.assertEqual(removed.decode(),row['removed_utf8']);self.assertEqual(len(removed),row['removed_bytes'])
        with self.assertRaises(ValueError):remove_sim_appendices(source+JOINT.encode(),config)
        with self.assertRaises(ValueError):remove_sim_appendices(source.replace(b'original',b'bad').replace(b'Entire',b'bad')+b'\nArtificial latency stress: unknown text\n',config)

    def test_selected_unique_cohorts_keep_one_slot_and_exact_task(self):
        with tempfile.TemporaryDirectory() as root:
            episode=self.fixture(root);output=Path(root)/'fixtures'
            result=build_fixtures([episode],output,{1:1,2:1,3:2})
            self.assertEqual(result['fixture_count'],4)
            manifest=json.loads((output/'fixtures.json').read_text());audit=json.loads((output/'audit.json').read_text())
            self.assertEqual(manifest['model_configuration']['max_output_tokens'],512)
            self.assertEqual([r['seq'] for r in audit['fixtures']],[0,4,8,12])
            self.assertTrue(all(r['slot']==0 for r in audit['fixtures']))
            for index,entry in enumerate(manifest['fixtures']):
                self.assertEqual(entry['prompt'],f'Full GAME task; obs 1:{index}; latency historical 2.7s; gating; visualmemory; action format.\n')
                for image_index,name in enumerate(entry['images']):
                    source=episode/f"decision_{audit['fixtures'][index]['seq']:05d}"/f'image_{image_index}.png'
                    self.assertEqual((output/name).read_bytes(),source.read_bytes())
            self.assertEqual(json.loads((output/'schema.json').read_text()),grounded_schema(1,48))
            with self.assertRaises(FileExistsError):build_fixtures([episode],output,{1:1,2:1,3:2})

    def test_add_completed_seeds_and_reject_short_or_duplicate_population(self):
        with tempfile.TemporaryDirectory() as root:
            first=self.fixture(root,'a',counts=(1,2,3),seed=1)
            second=self.fixture(root,'b',counts=(1,2,3),seed=2)
            with self.assertRaisesRegex(ValueError,'Insufficient'):build_fixtures([first],Path(root)/'bad',{1:1,2:1,3:2})
            self.assertFalse((Path(root)/'bad').exists())
            result=build_fixtures([first,second],Path(root)/'ok',{1:1,2:1,3:2});self.assertEqual(result['fixture_count'],4)
            duplicate=self.fixture(root,'c',counts=(1,2,3),seed=1)
            with self.assertRaisesRegex(ValueError,'Insufficient'):build_fixtures([first,duplicate],Path(root)/'dup',{1:1,2:1,3:2})

    def test_hash_schema_config_and_incomplete_sources_fail_closed(self):
        for change in ('prompt','native_schema','native_effort','image','candidate','cap','incomplete','race_difference'):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                episode=self.fixture(root)
                if change=='prompt':(episode/'decision_00000/prompt.txt').write_text('changed')
                elif change=='image':(episode/'decision_00000/image_0.png').write_bytes(b'changed')
                elif change=='incomplete':(episode/'summary.json').write_text(json.dumps({'complete':False}))
                elif change in ('cap','candidate'):
                    p=episode/'config.json';config=json.loads(p.read_text());config['max_output_tokens' if change=='cap' else 'candidate']=256 if change=='cap' else '';p.write_text(json.dumps(config))
                else:
                    p=episode/'decisions.jsonl';rows=[json.loads(x) for x in p.read_text().splitlines()]
                    if change=='native_schema':rows[0]['meta']['output_schema_sha256']='bad'
                    if change=='native_effort':rows[0]['meta']['effort']='high'
                    if change=='race_difference':rows[0]['prompt_sha256']='bad'
                    p.write_text(''.join(json.dumps(row)+'\n' for row in rows))
                with self.assertRaises(ValueError):build_fixtures([episode],Path(root)/'bad',{1:1,2:1,3:2})

    def test_explicit_stratum_quotas(self):
        self.assertEqual(parse_quotas('1:1,2:1,3:19'),{1:1,2:1,3:19})
        self.assertEqual(parse_quotas('1:1,2:1,3:13'),{1:1,2:1,3:13})
        for value in ('1:1,3:19','1:0,2:1,3:2','1:1,1:2,3:2','1=1,2=1,3=19'):
            with self.assertRaises(ValueError):parse_quotas(value)

if __name__=='__main__':unittest.main()
