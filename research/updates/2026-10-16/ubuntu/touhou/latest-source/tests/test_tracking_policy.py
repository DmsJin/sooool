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


class ReviewedPolicyTests(unittest.TestCase):
    def test_review_candidates_preserve_task_action_contract(self):
        for candidate in ('tracking_dodge_visual_v3','tracking_dodge_corridor_v3','tracking_dodge_visual_v4','tracking_dodge_visual_v5','tracking_dodge_groundtruth_v6'):
            text=make_prompt(candidate,{'image_frames':[1,31,61],'held':[0,1,1,0]}, {'structured':True,'wait_for_move':True}, {'control_age_p50_s':2.2,'control_age_p95_s':2.57})
            self.assertIn('"player":[x,y]',text)
            self.assertIn('"move":3',text)
            self.assertIn('duration is 1..48',text)
            if candidate in ('tracking_dodge_visual_v3','tracking_dodge_corridor_v3','tracking_dodge_groundtruth_v6'):self.assertIn('first legal answer',text)
            self.assertIn('3.44 pixels',text)
            self.assertLess(len(STRATEGIES[candidate]),len(STRATEGIES['tracking_dodge_safe_intercept_v2']))
            for forbidden in ('D01','D07','E01','tick1961','Math.sin','seed1'):
                self.assertNotIn(forbidden,text)

    def test_balanced_candidates_preserve_visual_action_protocol(self):
        observation={'image_frames':[1,31,61],'held':[0,1,1,0]}
        for candidate in ('tracking_dodge_balanced_v7','tracking_dodge_local_gap_v7','tracking_dodge_kinematic_v8','tracking_dodge_intercept_math_v8'):
            text=make_prompt(candidate,observation,{'structured':True,'wait_for_move':True},{'control_age_p50_s':2.2,'control_age_p95_s':2.57})
            self.assertIn('"player":[x,y]',text)
            self.assertIn('duration is 1..48',text)
            self.assertIn('first legal answer',text)
            self.assertIn('no target or duration is calculated for you',text)
            for private_data in ('D03','E08','robust_no_bomb_action_set','seed1'):
                self.assertNotIn(private_data,text)

    def test_zero_delay_fixture_is_not_claimed_as_real_measurement(self):
        for candidate in ('tracking_dodge_safe_intercept_v2','tracking_dodge_visual_v3'):
            text=make_prompt(candidate,{'image_frames':[1,31,61]}, {'structured':True}, {'control_age_kind':'instantaneous_diagnostic','control_age_p50_s':0,'control_age_p95_s':0})
            self.assertIn('zero simulated control delay',text)
            self.assertIn('not a measurement of real API latency',text)
            self.assertNotIn('measured across prior real API episodes',text)


class GroundTruthTimingTests(unittest.TestCase):
    def test_revised_reference_does_not_supply_private_action_table(self):
        text=STRATEGIES['tracking_dodge_groundtruth_v6']
        self.assertIn('Hypothetical timing example',text)
        self.assertIn('first claim proves neither',text)
        self.assertIn('multiple directions or speeds',text)
        self.assertNotIn('D03',text)
        self.assertNotIn('E07',text)
        self.assertNotIn('255',text)
        self.assertNotIn('2.2042',text)
        self.assertNotIn('robust_no_bomb_action_set',text)
