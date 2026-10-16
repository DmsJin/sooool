import os
import unittest

from research.environment import BrowserEnv


@unittest.skipUnless(os.environ.get('TOUHOU_TEST_URL'), 'Requires original frontend HTTP server')
class HumanInputReplayTest(unittest.TestCase):
    def test_real_keyboard_edges_reproduce_full_state_at_visual_frames(self):
        with BrowserEnv(os.environ['TOUHOU_TEST_URL']) as env:
            env.reset(1)
            env.page.evaluate('research.setHuman(true)')
            for key in ['z', 'Shift', 'ArrowRight']:
                env.page.keyboard.down(key)
            env.advance(175)
            env.page.keyboard.up('ArrowRight')
            env.page.keyboard.down('x')
            env.advance(2)
            env.page.keyboard.up('x')
            env.advance(3)
            env.page.evaluate("window.dispatchEvent(new Event('blur'))")
            env.advance(5)
            recorded = env.page.evaluate('research.drainHumanEvents()')
            expected = env.diagnostics()
            self.assertTrue(any(row['code'] == 'KeyX' and row['down'] for row in recorded['keys']))
            self.assertTrue(any(row['code'] == 'KeyX' and not row['down'] for row in recorded['keys']))
            self.assertTrue(any(row['reason'] == 'blur' for row in recorded['keys']))
            self.assertEqual(recorded['actions'][0]['visual_frame'], 165)
            self.assertEqual(expected['state']['player']['bombs'], 2)
            with self.assertRaises(Exception):
                env.apply([[0, 1, 1, 0, 1]])
            env.reset(1)
            env.page.evaluate('research.setHuman(true)')
            clock = env.clock()
            for row in recorded['actions']:
                clock = env.advance(row['visual_frame'] - clock['visual_frame'])
                env.page.evaluate('(a)=>research.setHumanAction(a)', row['action'])
            env.advance(expected['clock']['visual_frame'] - clock['visual_frame'])
            self.assertEqual(env.diagnostics()['state'], expected['state'])


if __name__ == '__main__':
    unittest.main()
