import copy
import unittest
from types import SimpleNamespace
from research.tracking_benchmark import recorded_api_delay,delay_conditions


def example():
    case=dict(source_seq=20,source_visual_frame=100,source_episode='/private/source')
    capture=dict(seq=20,visual_frame=100,cohort_id=20,image_sha256=['same'],capture_clock={'wall_ms':1000})
    winner=dict(capture,seq=21)
    action=dict(seq=21,observed_frame=100,visual_frame=314,capture_clock={'visual_frame':100},
        apply_clock={'wall_ms':4507.4},capture_to_apply_s=3.4)
    original=dict(issued=[capture,winner],actions=[action])
    return case,original


class RecordedDelayTests(unittest.TestCase):
    def test_cohort_winner_need_not_be_slot_zero(self):
        case,original=example();result=recorded_api_delay(case,original)
        self.assertEqual(result['source_applied_action_seq'],21)
        self.assertEqual(result['delay_visual_frames'],214)
        self.assertAlmostEqual(result['delay_s'],214/60)
        self.assertAlmostEqual(result['recorded_browser_age_s'],3.5074)

    def test_missing_ambiguous_or_wrong_cohort_rejected(self):
        case,original=example()
        for mutation in ['missing','duplicate','cohort','capture']:
            with self.subTest(mutation=mutation):
                changed=copy.deepcopy(original)
                if mutation=='missing':changed['actions']=[]
                elif mutation=='duplicate':changed['actions']*=2
                elif mutation=='cohort':changed['issued'][1]['cohort_id']=99
                else:changed['actions'][0]['capture_clock']['visual_frame']=99
                with self.assertRaises(ValueError):recorded_api_delay(case,changed)

    def test_human_fallback_must_be_explicit_and_assumed(self):
        args=SimpleNamespace(recorded_api_delays=True,human_recorded_fallback_s=None)
        with self.assertRaisesRegex(ValueError,'no recorded API age'):delay_conditions(args,{'source_run':'human'})
        args.human_recorded_fallback_s=2.69135
        condition=delay_conditions(args,{'source_run':'human'})[0]
        self.assertEqual(condition['delay_visual_frames'],162)
        self.assertEqual(condition['delay_kind'],'assumed_human_fallback_not_recorded')
        self.assertNotIn('source_applied_action_seq',condition)

    def test_recorded_diagnostic_cannot_enter_frozen_selector(self):
        from research.tracking_summary import summarize
        with self.assertRaisesRegex(ValueError,'not a completed tracking benchmark'):
            summarize({'kind':'private_tracking_recorded_delay_diagnostic_v1','complete':True},'base',16)

    def test_opt_in_does_not_change_frozen_fixed_ages(self):
        case,original=example()
        args=SimpleNamespace(recorded_api_delays=False,delays=[2.69135,3.170205])
        result=delay_conditions(args,case,original)
        self.assertEqual([r['delay_visual_frames'] for r in result],[162,191])
        self.assertEqual([r['delay_s'] for r in result],args.delays)

if __name__=='__main__':unittest.main()
