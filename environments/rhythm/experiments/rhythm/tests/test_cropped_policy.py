import io
import unittest

from PIL import Image

from experiments.rhythm.cropped_policy import crop_observation, prompt
from experiments.rhythm.policy import parse
from experiments.rhythm.visual_env import Observation


class CroppedPolicyTests(unittest.TestCase):
    def test_crop_preserves_pixels_coordinates_clock_and_timing_geometry(self):
        original = Image.new('RGB', (390, 688))
        original.putpixel((33, 120), (11, 180, 240))
        buffer = io.BytesIO()
        original.save(buffer, format='PNG')
        obs = Observation(buffer.getvalue(), 1.4, 1.4, 1.4,
                          {'width': 390, 'height': 688, 'hitline_y': 600,
                           'canvas_top': 0, 'frame_age_s': .02}, 'playing')
        cropped = crop_observation(obs)
        with Image.open(io.BytesIO(cropped.png)) as image:
            self.assertEqual(image.size, (390, 200))
            self.assertEqual(image.tobytes(), original.crop((0, 0, 390, 200)).tobytes())
        self.assertEqual(cropped.time_s, obs.time_s)
        self.assertEqual(cropped.geometry['hitline_y'], 600)
        self.assertEqual(cropped.geometry['height'], 200)
        self.assertEqual(obs.geometry['height'], 688)
        self.assertEqual(parse('[[0,120]]', cropped, 'pixels_cropped_v1'),
                         parse('[[0,120]]', obs, 'pixels'))
        self.assertLess(len(prompt(cropped)), 200)


if __name__ == '__main__':
    unittest.main()
