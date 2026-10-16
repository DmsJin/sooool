import copy,json,unittest
from research.wire_schema import decision_schema,grounded_schema,FORECAST_CANDIDATES
from research.scheduler import parse_plan
from research.policies import make_prompt

class ForecastSchemaTests(unittest.TestCase):
    def test_historical_candidates_keep_identical_schema(self):
        for name in ('tracking_dodge_safe_intercept_v2','tracking_dodge_kinematic_v8','tracking_dodge_balanced_v7'):
            self.assertEqual(decision_schema(name,1,48),grounded_schema(1,48))

    def test_prediction_is_ignored_by_action_executor_even_when_wrong(self):
        action={'move':7,'shoot':1,'focus':0,'bomb':0,'duration':26}
        answer={'player':[285,400],'boss':[240,88],'aim_x':170,
                'forecast':{'boss_vx_px_s':-20,'player_at_apply':[285,400],'endpoint':[999,999],'boss_at_shot_x':170},'plan':[action]}
        self.assertEqual(parse_plan(answer),parse_plan({'plan':[action]}))
        other=copy.deepcopy(answer);other['forecast']=None
        self.assertEqual(parse_plan(other),parse_plan(answer))

    def test_forecast_is_required_in_model_schema_and_defined_in_prompt(self):
        for candidate in FORECAST_CANDIDATES:
            schema=decision_schema(candidate,1,48)
            self.assertIn('forecast',schema['required'])
            self.assertFalse(schema['properties']['forecast']['additionalProperties'])
            self.assertEqual(schema['properties']['plan'],grounded_schema(1,48)['properties']['plan'])
            text=make_prompt(candidate,{'image_frames':[0,30,60]}, {'structured':True,'wait_for_move':True}, {})
            self.assertIn('executor ignores them',text)
            self.assertIn('first legal answer',text)
            self.assertIn('"forecast"',text)
            for private in ('E02','E08','robust_no_bomb_action_set'):
                self.assertNotIn(private,text)
