import subprocess
import unittest
from research.policies import make_prompt, STRATEGIES
from research.tracking_cases import extract_past_memory


class TrackingPolicyTests(unittest.TestCase):
    def test_historical_prompts_unchanged(self):
        old={};exec(subprocess.check_output(['git','show','b0a9793:research/policies.py'],text=True),old)
        observation={'image_frames':[10,40,70],'held':[0,1,1,0]}
        for candidate in old['STRATEGIES']:
            for structured in (False,True):
                config={'structured':structured,'wait_for_move':True,'pixel_controls':True}
                self.assertEqual(make_prompt(candidate,observation,config,{}),old['make_prompt'](candidate,observation,config,{}))

    def test_new_candidates_keep_visual_action_contract(self):
        for candidate in ('tracking_dodge_intercept_hold','tracking_dodge_turn_guard'):
            text=make_prompt(candidate,{'image_frames':[10,40,70]}, {'structured':True}, {})
            self.assertIn('"player":[x,y]',text)
            self.assertIn('"move":3',text)
            self.assertIn('movement has ended and the next response is pending',text)
            self.assertIn('never an automatic tracker',text)

    def test_memory_rejects_future_and_extra_state(self):
        prefix='Your own past visual estimates (not engine truth), with each observed frame and boss coordinate: '
        self.assertEqual(extract_past_memory(prefix+'[{"frame":5,"boss":[100,86]}]. trailing',10),[{'frame':5,'boss':[100,86]}])
        for value in ('[{"frame":11,"boss":[100,86]}]','[{"frame":5,"boss":[100,86],"future":1}]'):
            with self.assertRaises(ValueError):extract_past_memory(prefix+value,10)

    def test_v2_candidates_explicitly_check_idle_and_keep_safety_first(self):
        baseline=STRATEGIES['tracking_dodge_adaptive']
        for name in ('tracking_dodge_safe_intercept_v2','tracking_dodge_safe_corridor_v2'):
            delta=STRATEGIES[name][len(baseline):]
            self.assertTrue(STRATEGIES[name].startswith(baseline))
            self.assertLess(len(delta),1300)
            text=make_prompt(name,{'image_frames':[10,40,70]}, {'structured':True}, {})
            self.assertIn('"player":[x,y]',text)
            self.assertIn('next slow',delta)
            self.assertIn('stay',delta.lower())
            self.assertIn('safety',delta.lower())
