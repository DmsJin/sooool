import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'environments/asterix'))
import runner

class DefaultAsterix(unittest.TestCase):
    def test_exact_selected_task_and_recipe(self):
        recipe=json.loads((ROOT/'recipes/asterix.json').read_text())
        metadata=json.loads((ROOT/'policies/asterix/v28/policy.json').read_text())
        self.assertEqual(recipe,json.loads((ROOT/'recipes/asterix-v28.json').read_text()))
        self.assertEqual((recipe['args']['controller'],recipe['native_workers'],recipe['args']['virtual_capacity']),('direct',1,1))
        task,delays=runner.build_task(ROOT,recipe,'simulation')
        self.assertEqual(task,(ROOT/'artifacts/asterix/serial-selected/english_reason/prompt.txt').read_text())
        self.assertEqual(len(delays),536)
        self.assertEqual(hashlib.sha256((ROOT/recipe['prompt']).read_bytes()).hexdigest(),metadata['prompt_sha256'])

    def test_realtime_task_describes_actual_clock(self):
        recipe=json.loads((ROOT/'recipes/asterix.json').read_text())
        task,_=runner.build_task(ROOT,recipe,'realtime')
        self.assertIn('computation wall time DOES advance',task)
        self.assertNotIn('computation wall time does not advance',task)
        self.assertNotIn('available only after a sampled',task)

if __name__=='__main__':unittest.main()
