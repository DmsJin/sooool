"""Zero-inference auditor tests against a real completed ALE artifact."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from verify_food_comparison import audit


@unittest.skipUnless(os.environ.get('ASTERIX_AUDIT_FIXTURE'), 'Requires completed ALE artifact')
class ReplayAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        original=Path(os.environ['ASTERIX_AUDIT_FIXTURE'])
        root=Path(self.temporary.name)
        self.directory=root/'seed';self.directory.mkdir()
        for name in ('summary.json','steps.jsonl','decisions.jsonl','actions.json','ignored_commands.json'):
            shutil.copyfile(original/name,self.directory/name)
        shutil.copyfile(original.parent/'config.json',root/'config.json')
        self.profile=Path(os.environ['ASTERIX_AUDIT_PROFILE'])

    def test_real_completed_artifact_passes(self):
        result=audit(self.directory,self.profile)
        self.assertEqual(result['frames'],1200)
        self.assertGreater(result['verified_request_images'],0)
        self.assertEqual(result['verification_model_calls'],0)

    def test_wrong_observation_hash_is_rejected(self):
        path=self.directory/'decisions.jsonl'
        rows=[json.loads(x) for x in path.read_text().splitlines()]
        rows[0]['image_sha256'][0]='0'*64
        path.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        with self.assertRaises(AssertionError):audit(self.directory,self.profile)

    def test_invented_reward_is_rejected(self):
        path=self.directory/'steps.jsonl'
        rows=[json.loads(x) for x in path.read_text().splitlines()]
        rows[0]['reward']=999
        rows[0]['score']=999
        path.write_text(''.join(json.dumps(x)+'\n' for x in rows))
        with self.assertRaises(AssertionError):audit(self.directory,self.profile)

    def test_reused_replies_are_not_called_fresh(self):
        path=self.directory/'summary.json'
        data=json.loads(path.read_text());data['replayed_calls']=1
        path.write_text(json.dumps(data))
        with self.assertRaises(AssertionError):audit(self.directory,self.profile)


if __name__=='__main__':unittest.main()
