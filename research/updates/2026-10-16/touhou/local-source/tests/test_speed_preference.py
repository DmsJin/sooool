import json
import unittest

from research.policies import STRATEGIES, SPEED_PREFERENCE_REPLACEMENTS_V13, make_prompt
from research.wire_schema import decision_schema, FORECAST_CANDIDATES


class SpeedPreferenceAblationTests(unittest.TestCase):
    source='tracking_dodge_safe_intercept_v2'
    candidate='tracking_dodge_speed_unconflicted_v13'

    def restore(self,text):
        for old,new in SPEED_PREFERENCE_REPLACEMENTS_V13:
            self.assertEqual(text.count(new),1)
            self.assertNotIn(old,text)
            text=text.replace(new,old)
        return text

    def test_strategy_changes_exactly_two_inherited_sentences(self):
        source=STRATEGIES[self.source];new=STRATEGIES[self.candidate]
        self.assertEqual(self.restore(new),source)
        self.assertIn(STRATEGIES['tracking_dodge_adaptive'],source)
        self.assertNotIn(STRATEGIES['tracking_dodge_adaptive'],new)
        self.assertLessEqual(len(new)-len(source),32)

    def test_schema_remains_the_four_field_v2_contract(self):
        self.assertNotIn(self.candidate,FORECAST_CANDIDATES)
        for chunks,duration in ((1,48),(3,24)):
            source=decision_schema(self.source,chunks,duration)
            candidate=decision_schema(self.candidate,chunks,duration)
            self.assertEqual(json.dumps(source),json.dumps(candidate))
            self.assertEqual(candidate['required'],['player','boss','aim_x','plan'])

    def test_all_other_task_controls_bomb_grounding_and_cohort_text_identical(self):
        observation={'image_frames':[60,90,120],'held':[0,1,1,0],
                     'visual_memory':[{'frame':30,'boss':[220,86]}]}
        profiles=[{}, {'p50_s':2.2,'p95_s':2.6,'control_age_p50_s':2.2,'control_age_p95_s':2.6},
                  {'control_age_kind':'instantaneous_diagnostic'}]
        for intro in (0,135):
            for wait in (False,True):
                for structured in (False,True):
                    for profile in profiles:
                        obs={**observation,'clock':{'intro':intro}}
                        config={'wait_for_move':wait,'structured':structured,'pixel_controls':True,
                                'chunk_size':1,'max_duration':48,'speed':1,'decision_fanout':4}
                        plan={'action':[7,1,1,0],'end':140}
                        before=make_prompt(self.source,obs,config,profile,plan)
                        after=make_prompt(self.candidate,obs,config,profile,plan)
                        self.assertEqual(self.restore(after).encode(),before.encode())
                        self.assertNotIn('forecast',after)
                        for private in ('E02','E04','E08','normal30','robust_no_bomb_action_set','engine boss formula'):
                            self.assertNotIn(private,after)


if __name__=='__main__':unittest.main()
