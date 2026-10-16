import json
from pathlib import Path
import tempfile
import unittest
from runtime.evaluation import assess,record_run

class Records(unittest.TestCase):
    def test_partial_summary_is_interrupted_without_a_failure_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'manifest.json').write_text(json.dumps({'game':'asterix','mode':'subscription_with_simulated_profile','recipe':{}}))
            (p/'summary.json').write_text(json.dumps({'episodes':[{'status':'interrupted','error':{'message':'timeout'}}]}))
            self.assertEqual(record_run(p)['status'],'interrupted')

    def test_failures_and_append_only_decisions_keep_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/'manifest.json').write_text(json.dumps({'game':'asterix','mode':'real_time_subscription','recipe':{'policy':'v28'}}))
            (p/'failure.json').write_text('{"message":"interrupted"}')
            record=record_run(p)
            self.assertEqual(record['status'],'interrupted')
            self.assertIsNone(record['summary'])
            assess(p,'diagnostic','Provider failure is not a game loss.')
            assess(p,'reject','Retry under a fresh run directory.')
            rows=[json.loads(x) for x in (p/'assessments.jsonl').read_text().splitlines()]
            self.assertEqual([r['decision'] for r in rows],['diagnostic','reject'])
            self.assertTrue(all(r['manifest_sha256']==record['manifest_sha256'] for r in rows))

if __name__=='__main__':unittest.main()
