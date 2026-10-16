import unittest

from research.policies import STRATEGIES, make_prompt


class ControlAgePromptTests(unittest.TestCase):
    def setUp(self):
        self.observation = {'image_frames': [180, 210, 240], 'held': [0, 1, 1, 0]}
        self.profile = {'p50_s': 1.882, 'p95_s': 3.136}

    def test_optional_pair_preserves_legacy_prompt_when_incomplete(self):
        for candidate in STRATEGIES:
            for structured in [False, True]:
                config = {'chunk_size': 1, 'structured': structured}
                baseline = make_prompt(candidate, self.observation, config, self.profile)
                for extra in [{}, {'control_age_p50_s': 1.4}, {'control_age_p95_s': 1.8}]:
                    with self.subTest(candidate=candidate, structured=structured, extra=extra):
                        self.assertEqual(baseline, make_prompt(candidate, self.observation,
                                                               config, self.profile | extra))

    def test_measured_age_distinguished_from_marginal_request_latency(self):
        profile = self.profile | {'control_age_p50_s': 1.4, 'control_age_p95_s': 1.8}
        for structured in [False, True]:
            prompt = make_prompt('grounded_macro', self.observation,
                                 {'chunk_size': 1, 'structured': structured}, profile)
            self.assertIn('Per-request marginal API complete-action delay: median 1.882s, P95 3.136s', prompt)
            self.assertIn('Observed screenshot-to-selected-action-application delay: median 1.400s, P95 1.800s', prompt)
            self.assertIn('measured across prior real API episodes', prompt)
            self.assertIn('including race selection and actuator overhead', prompt)
            self.assertIn('not the known delay of this request', prompt)

    def test_control_age_changes_only_latency_context(self):
        config = {'chunk_size': 3, 'structured': True, 'wait_for_move': True}
        baseline = make_prompt('grounded_macro', self.observation, config, self.profile)
        profile = self.profile | {'control_age_p50_s': 1.4, 'control_age_p95_s': 1.8,
                                  'current_request_delay': 'PRIVATE_ORACLE',
                                  'entity_state': 'PRIVATE_STATE'}
        measured = make_prompt('grounded_macro', self.observation, config, profile)
        old_lines = [line for line in baseline.splitlines() if 'Measured unloaded API' not in line]
        new_lines = [line for line in measured.splitlines() if not any(label in line for label in (
            'Per-request marginal API', 'Observed screenshot-to-selected-action-application'))]
        self.assertEqual(old_lines, new_lines)
        self.assertNotIn('PRIVATE_', measured)

    def test_early_forecast_is_explicitly_modeled(self):
        profile = self.profile | {'control_age_kind':'modeled_early_legal',
                                  'control_age_p50_s':2.23,'control_age_p95_s':2.77}
        prompt=make_prompt('tracking_dodge_adaptive',self.observation,
                           {'chunk_size':1,'structured':True},profile)
        self.assertIn('Early delivery has not yet been measured end to end',prompt)
        self.assertIn('two-image stratum has only one serial sample',prompt)
        self.assertNotIn('Observed screenshot-to-selected-action-application',prompt)

    def test_early_transport_uses_legal_marginal_and_modeled_context(self):
        profile=self.profile | {'control_age_kind':'modeled_early_prompt_transport',
                                'control_age_p50_s':2.6,'control_age_p95_s':3.2,
                                'transport_audit':'PRIVATE_TIMING', 'actor_context':'PRIVATE_INJECTION'}
        prompt=make_prompt('tracking_dodge_intercept_hold',self.observation,
                           {'chunk_size':1,'structured':True},profile)
        self.assertIn('Per-request marginal API legal-action delay',prompt)
        self.assertIn('not newly measured concurrent performance',prompt)
        self.assertNotIn('Observed screenshot-to-selected-action-application',prompt)
        self.assertNotIn('PRIVATE_',prompt)

    def test_static_pixel_controls_opt_in_preserves_default(self):
        config = {'chunk_size': 1, 'structured': True}
        baseline = make_prompt('grounded_macro', self.observation, config, self.profile)
        self.assertEqual(baseline, make_prompt('grounded_macro', self.observation,
                                              config | {'pixel_controls': False}, self.profile))
        enabled = make_prompt('grounded_macro', self.observation,
                              config | {'pixel_controls': True}, self.profile)
        self.assertTrue(enabled.startswith(baseline))
        for phrase in ['3.44 pixels per logical frame', '1.6 pixels per logical frame',
                       'divide the horizontal component by sqrt(2)',
                       '60 frames per game second', 'not a live player position',
                       'choose a safe movement direction, focus, and duration yourself',
                       'do not have to reach aim_x completely']:
            self.assertIn(phrase, enabled)

    def test_visual_memory_absent_or_empty_preserves_default(self):
        config = {'chunk_size': 1, 'structured': True}
        baseline = make_prompt('grounded_macro', self.observation, config, self.profile)
        for value in [None, []]:
            self.assertEqual(baseline, make_prompt('grounded_macro',
                             self.observation | {'visual_memory': value}, config, self.profile))

    def test_visual_memory_passed_verbatim_as_model_estimates(self):
        config = {'chunk_size': 1, 'structured': True}
        memory = [{'frame': 90, 'boss': [260, 88]}, {'frame': 180, 'boss': [282, 86]}]
        baseline = make_prompt('grounded_macro', self.observation, config, self.profile)
        prompt = make_prompt('grounded_macro', self.observation | {'visual_memory': memory},
                             config, self.profile)
        self.assertTrue(prompt.startswith(baseline))
        self.assertIn('[{"frame":90,"boss":[260,88]},{"frame":180,"boss":[282,86]}]', prompt)
        self.assertIn('not engine truth', prompt)
        self.assertIn('newest screenshot is authoritative', prompt)
        self.assertIn('never treat old positions as current', prompt)


if __name__ == '__main__':
    unittest.main()
