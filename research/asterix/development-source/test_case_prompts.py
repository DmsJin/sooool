import unittest
from summarize_case_prompts import summarize

class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.labels = [{'case_id':'C01a','human_candidate_safe_actions':[1,5,6]},
                       {'case_id':'C03a','human_candidate_safe_actions':None},
                       {'case_id':'D01a','human_candidate_safe_actions':[3]}]
    def row(self,action,case='C01a',repeat=0):
        return {'variant':'v1','case_id':case,'repeat':repeat,'action':action}
    def test_accepts_all_members_of_candidate_set(self):
        result=summarize([self.row(1,repeat=0),self.row(6,repeat=1),self.row(2,repeat=2)],self.labels)
        self.assertEqual(result['variants']['v1']['agrees'],2)
        self.assertEqual(result['variants']['v1']['calls'],3)
    def test_invalid_outputs_are_failures_not_dropped(self):
        result=summarize([self.row(None,repeat=0),self.row(True,repeat=1)],self.labels)['variants']['v1']
        self.assertEqual(result['valid_actions'],0)
        self.assertEqual(result['calls'],2)
        self.assertEqual(result['agrees'],0)
    def test_duplicate_results_rejected(self):
        with self.assertRaises(ValueError): summarize([self.row(1),self.row(1)],self.labels)
    def test_unlabeled_and_execution_cases_rejected(self):
        for case in ['C03a','D01a']:
            with self.assertRaises(ValueError): summarize([self.row(1,case)],self.labels)

if __name__ == '__main__': unittest.main()
