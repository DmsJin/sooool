import json
import unittest

from research.policies import CURVATURE_CHECK_V14, STRATEGIES, make_prompt
from research.wire_schema import decision_schema, FORECAST_CANDIDATES


class CurvatureAblationTests(unittest.TestCase):
    pairs=(('tracking_dodge_safe_intercept_v2','tracking_dodge_curvature_v14'),
           ('tracking_dodge_speed_unconflicted_v13','tracking_dodge_speed_curvature_v14'))

    def test_same_short_appendix_and_unchanged_source_strategies(self):
        self.assertGreaterEqual(len(CURVATURE_CHECK_V14.split()),80)
        self.assertLessEqual(len(CURVATURE_CHECK_V14.split()),115)
        for source,candidate in self.pairs:
            self.assertEqual(STRATEGIES[candidate],STRATEGIES[source]+'\n'+CURVATURE_CHECK_V14)
            self.assertNotIn(CURVATURE_CHECK_V14,STRATEGIES[source])
        self.assertIn('interval-midpoint',CURVATURE_CHECK_V14)
        self.assertIn('without enough history',CURVATURE_CHECK_V14)
        self.assertIn('noisy',CURVATURE_CHECK_V14)
        self.assertIn('never extrapolate it indefinitely',CURVATURE_CHECK_V14)
        self.assertIn('spawn position is not a motion boundary',CURVATURE_CHECK_V14)
        for private in ('E04','seed','sin(','Math.sin','150','robust_no_bomb_action_set'):
            self.assertNotIn(private,CURVATURE_CHECK_V14)

    def test_original_four_fields_and_cohort_grounding_controls_unchanged(self):
        for source,candidate in self.pairs:
            self.assertNotIn(candidate,FORECAST_CANDIDATES)
            schema=decision_schema(candidate,1,48)
            self.assertEqual(schema['required'],['player','boss','aim_x','plan'])
            self.assertEqual(json.dumps(schema),json.dumps(decision_schema(source,1,48)))
            for frames in ([0],[1,31,61]):
                for intro in (0,135):
                    for wait in (False,True):
                        for structured in (False,True):
                            obs={'image_frames':frames,'held':[0,1,1,0],'clock':{'intro':intro},
                                 'visual_memory':[{'frame':0,'boss':[224,86]}]}
                            config={'wait_for_move':wait,'structured':structured,'pixel_controls':True,
                                    'chunk_size':1,'max_duration':48,'speed':1,'decision_fanout':4}
                            profile={'p50_s':2.2,'p95_s':2.6,'control_age_p50_s':2.2,'control_age_p95_s':2.6}
                            before=make_prompt(source,obs,config,profile)
                            after=make_prompt(candidate,obs,config,profile)
                            self.assertEqual(after.count(CURVATURE_CHECK_V14),1)
                            self.assertEqual(after.replace('\n'+CURVATURE_CHECK_V14,'').encode(),before.encode())
                            self.assertNotIn('"forecast"',after)


if __name__=='__main__':unittest.main()
