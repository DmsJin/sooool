import json
import unittest
from experiments.rhythm.model_outer_ab import grade, schedule_pairs, token_metrics


class OuterABTests(unittest.TestCase):
    def test_randomization_is_reproducible_and_paired(self):
        inputs=[{'index':i} for i in range(12)]
        pairs=schedule_pairs(inputs,2,17)
        self.assertEqual(pairs,schedule_pairs(inputs,2,17))
        self.assertEqual(len(pairs),24)
        self.assertTrue(all(set(pair['order'])=={'baseline','minimal'} for pair in pairs))
        self.assertEqual(len({(pair['input_index'],pair['repeat']) for pair in pairs}),24)

    def test_trusted_grader_does_not_backdate_late_execution(self):
        answer=json.dumps({'v':1,'a':[['note','d',11000.125,11120.5]]})
        item={'trusted_game_s':.5,'external_now_ms':10500}
        chart={'notes':[{'time':1.000125,'lane':0}]}
        result=grade(answer,item,chart,clock_offset_ms=10000,full_return_s=2,api_delays=[.4,.6,.7])
        tap=result['tap_grades'][0]
        self.assertEqual(tap['at_ms'],11000.125)
        self.assertEqual(tap['absolute_error_ms'],0)
        self.assertLess(tap['hypothetical_return_lead_ms'],0)
        self.assertAlmostEqual(tap['api_unexpired_probability'],2/3)
        self.assertAlmostEqual(tap['api_within_55ms_probability'],1/3)
        self.assertAlmostEqual(tap['api_within_110ms_probability'],2/3)

    def test_schema_empty_coverage_and_cache_are_separate(self):
        item={'trusted_game_s':.5,'external_now_ms':10500}
        chart={'notes':[{'time':1,'lane':0}]}
        self.assertFalse(grade('script()',item,chart,clock_offset_ms=10000,full_return_s=1)['schema_valid'])
        result=grade('{"v":1,"a":[]}',item,chart,clock_offset_ms=10000,full_return_s=1,api_delays=[.4])
        self.assertTrue(result['empty'])
        self.assertEqual(result['visible_coverage_180ms'],0)
        self.assertEqual(token_metrics({'token_usage':{'last':{'inputTokens':100,'cachedInputTokens':90}}})['cachedInputTokens'],90)


if __name__=='__main__':unittest.main()
