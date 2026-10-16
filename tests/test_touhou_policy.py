import hashlib
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'environments/touhou'))
from research.policies import make_prompt,STRATEGIES
from research.live_summary import brief_prompt

class SelectedPolicy(unittest.TestCase):
    def test_selected_task_is_identical_to_live_source_fixture(self):
        p=ROOT/'policies/touhou/tracking-safe-intercept-v2';f=json.loads((p/'fixtures/input.json').read_text())
        task=brief_prompt(make_prompt('tracking_dodge_safe_intercept_v2',f['observation'],f['config'],f['profile']), 'en')
        self.assertEqual(task,(p/'fixtures/task-prompt.txt').read_text())
        self.assertEqual(hashlib.sha256(task.encode()).hexdigest(),f['expected_prompt_sha256'])
        self.assertEqual(STRATEGIES['tracking_dodge_safe_intercept_v2'],(p/'policy.txt').read_text())
    def test_no_unselected_later_candidate_in_active_policy(self):
        self.assertNotIn('tracking_dodge_forecast_v9',STRATEGIES)
        self.assertNotIn('tracking_dodge_speed_unconflicted_v13',STRATEGIES)
    def test_realtime_and_development_use_same_strategy_and_english_schema(self):
        sim=json.loads((ROOT/'recipes/touhou.json').read_text());live=json.loads((ROOT/'recipes/touhou-realtime.json').read_text())
        for k in ('candidate','chunk_size','max_duration','structured','brief_language','decision_brief','capture_stride','history_spacing_frames'):
            self.assertEqual(sim['args'][k],live['args'][k],k)
        self.assertEqual(sim['args']['provider'],'subscription');self.assertEqual(live['args']['provider'],'api')
