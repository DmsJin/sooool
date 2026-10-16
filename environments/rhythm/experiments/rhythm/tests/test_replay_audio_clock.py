import unittest
from experiments.rhythm.render_decision_replay import audio_origin


class ReplayAudioClockTests(unittest.TestCase):
    def test_startup_clock_is_not_used_to_shift_whole_video(self):
        rows=[{'external_ms':1000,'audio_s':0,'state':'playing'},
              {'external_ms':6070,'audio_s':5,'state':'playing'},
              {'external_ms':11072,'audio_s':10,'state':'playing'},
              {'external_ms':16071,'audio_s':15,'state':'playing'}]
        self.assertEqual(audio_origin(rows),1071)

    def test_paused_and_result_samples_do_not_bias_clock(self):
        rows=[{'external_ms':1000,'audio_s':0,'state':'playing'},
              {'external_ms':6070,'audio_s':5,'state':'playing'},
              {'external_ms':15000,'audio_s':5,'state':'paused','paused':True},
              {'external_ms':25000,'audio_s':17,'state':'result'}]
        self.assertEqual(audio_origin(rows),1070)

    def test_short_legacy_capture_has_explicit_startup_fallback(self):
        self.assertEqual(audio_origin([{'external_ms':1030,'audio_s':.03,'state':'playing'}]),1000)
