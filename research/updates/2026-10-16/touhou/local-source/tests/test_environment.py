import os
import time
import unittest
from hashlib import sha256
from pathlib import Path
from research.environment import BrowserEnv


@unittest.skipUnless(os.environ.get('TOUHOU_TEST_URL'), 'Requires original frontend HTTP server')
class EnvironmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = BrowserEnv(os.environ['TOUHOU_TEST_URL'])

    @classmethod
    def tearDownClass(cls):
        cls.env.close()

    def test_sim_clock_capture_and_expiry(self):
        env = self.env
        env.reset(1)
        before = env.clock()
        time.sleep(.12)
        self.assertEqual(env.clock()['visual_frame'], before['visual_frame'])
        env.apply([[3, 1, 1, 0, 12]])
        env.advance(165)
        self.assertEqual(env.clock()['frame'], 0)
        self.assertEqual(env.clock()['intro'], 0)
        x = env.diagnostics()['state']['player']['x']
        env.advance(12)
        self.assertGreater(env.diagnostics()['state']['player']['x'], x)
        env.advance(1)
        self.assertEqual(env.clock()['held'], [0, 1, 1, 0])
        shot = env.capture()
        self.assertEqual(shot['png'][:8], b'\x89PNG\r\n\x1a\n')
        self.assertEqual(shot['frame'], shot['clock']['frame'])
        self.assertEqual(set(shot), {'png', 'frame', 'held', 'clock'})
        first_hash = sha256(shot['png']).hexdigest()
        env.reset(1)
        env.apply([[3, 1, 1, 0, 12]])
        env.advance(178)
        self.assertEqual(first_hash, sha256(env.capture()['png']).hexdigest())

    def test_bomb_edge_and_replacement(self):
        env = self.env
        env.reset(1)
        env.advance(165)
        env.apply([[0, 1, 1, 1, 40], [3, 1, 1, 0, 60]])
        env.advance(35)
        self.assertEqual(env.diagnostics()['state']['player']['bombs'], 2)
        env.apply([[0, 1, 1, 0, 120], [0, 1, 1, 1, 2]])
        env.advance(122)
        self.assertEqual(env.diagnostics()['state']['player']['bombs'], 1)
        env.advance(1)
        self.assertEqual(env.clock()['held'], [0, 1, 1, 0])
        with self.assertRaises(Exception):
            env.apply([[10, 1, 1, 0, 4]])

    def test_realtime_independent_of_python_and_no_gap_clip(self):
        env = self.env
        env.reset(1, mode='realtime', speed=1)
        time.sleep(.3)
        first = env.clock()['visual_frame']
        self.assertGreaterEqual(first, 10)
        env.page.evaluate('()=>{const end=performance.now()+260;while(performance.now()<end){}}')
        time.sleep(.1)
        self.assertGreaterEqual(env.clock()['visual_frame']-first, 17)
        with self.assertRaises(Exception):
            env.advance(1)
        for _ in range(3):
            self.assertEqual(env.capture()['frame'], 0)

    def test_engine_frozen(self):
        expected = '348e81340d4a09f8b488193daf0b4e395afa2755d34f249585ff5e1ffe787aa4'
        for path in ['dist/engine.mjs', 'python/touhou_gym/engine/engine.mjs']:
            self.assertEqual(sha256(Path(path).read_bytes()).hexdigest(), expected)

    def test_idle_sim_avoids_redraw_but_step_and_realtime_render(self):
        env = self.env
        env.reset(1)
        env.page.evaluate('''()=>{
            window.gameDrawCount=0;
            const original=CanvasRenderingContext2D.prototype.drawImage;
            CanvasRenderingContext2D.prototype.drawImage=function(...args){
                if(this.canvas.id==='game')window.gameDrawCount++;
                return original.apply(this,args);
            };
        }''')
        time.sleep(.25)
        self.assertEqual(env.page.evaluate('gameDrawCount'), 0)
        env.advance(1)
        self.assertGreater(env.page.evaluate('gameDrawCount'), 0)
        env.reset(1, mode='realtime')
        env.page.evaluate('window.gameDrawCount=0')
        time.sleep(.25)
        self.assertGreater(env.page.evaluate('gameDrawCount'), 0)


if __name__ == '__main__':
    unittest.main()
