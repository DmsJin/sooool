import copy
import unittest

from research.state_compare import compare_engine_state


class ReplayStateComparisonTests(unittest.TestCase):
    def setUp(self):
        self.state={'hits':0,'alive':True,'status':'playing','bullets':[{'x':1.0,'vx':.1}]}

    def test_cross_v8_float_ulp_is_reported_and_bounded(self):
        changed=copy.deepcopy(self.state);changed['bullets'][0]['vx']+=6e-16
        result=compare_engine_state(changed,self.state)
        self.assertFalse(result['exact']);self.assertTrue(result['bounded_float'])
        self.assertGreater(result['max_abs_float_difference'],0)
        self.assertEqual(len(result['differences']),1)

    def test_real_position_change_rejected(self):
        changed=copy.deepcopy(self.state);changed['bullets'][0]['x']+=1e-3
        self.assertFalse(compare_engine_state(changed,self.state)['bounded_float'])

    def test_integer_boolean_types_and_structure_are_strict(self):
        changes=[dict(hits=1),dict(alive=1),dict(hits=0.0),dict(bullets=[]),dict(extra=0)]
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(compare_engine_state(self.state|change,self.state)['bounded_float'])
        missing=copy.deepcopy(self.state);del missing['hits']
        self.assertFalse(compare_engine_state(missing,self.state)['bounded_float'])

    def test_nonfinite_float_not_equal(self):
        for value in [float('nan'),float('inf')]:
            self.assertFalse(compare_engine_state({'x':value},{'x':value})['bounded_float'])


if __name__=='__main__':unittest.main()
