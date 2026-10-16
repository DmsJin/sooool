import unittest
from experiments.rhythm.model_native import acceptance


class NativeAcceptanceTests(unittest.TestCase):
    def test_short_episode_must_judge_every_note_and_keep_full_combo(self):
        result={'state':'result','judged':33,'total_notes':33,'counts':{'miss':0},'max_combo':33}
        self.assertEqual(acceptance(result,True,.07,expected_notes=33),(True,True))
        result['judged']=32
        self.assertEqual(acceptance(result,True,.07,expected_notes=33),(False,False))
        result['judged']=33;result['max_combo']=2
        self.assertEqual(acceptance(result,True,.07,expected_notes=33),(True,False))

    def test_empty_presses_can_break_combo_without_missed_notes(self):
        result={'state':'result','judged':52,'total_notes':52,
                'counts':{'miss':0},'max_combo':2}
        self.assertEqual(acceptance(result,True,.07),(True,False))
        result['max_combo']=52
        self.assertEqual(acceptance(result,True,.07),(True,True))
        self.assertEqual(acceptance(result,True,.5),(True,False))
        self.assertEqual(acceptance(result,False,.07),(True,False))

