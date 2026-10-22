"""Long-lived page, pixel and literal-input contracts owned by the Rhythm environment."""
import io
from pathlib import Path
import unittest

from gymnasium.utils.env_checker import check_env
from PIL import Image
from rhythm_gym import RhythmEnv

from experiments.rhythm.model_env import ModelVisualEnv
from runtime.run_support import serve


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def test_page_capture_literal_key_and_cleanup_in_both_clock_modes(self):
        root = Path(__file__).resolve().parents[3]
        for virtual in (True, False):
            with self.subTest(virtual=virtual), serve(root / "dist") as url:
                async with ModelVisualEnv(url, virtual=virtual, chart_path=root / "dist/chart.json") as env:
                    errors = []
                    env._page.on("pageerror", lambda error: errors.append(str(error)))
                    await env.start()
                    shot = await env.capture()
                    self.assertEqual(Image.open(io.BytesIO(shot["png"])).size, (390, 844))
                    snapshot = await env.snapshot()
                    now = snapshot["clock_ms"]
                    result = await env.apply({"version": 0, "cancel_ids": [], "taps": [
                        {"id": "ci-key", "key": "d", "at_ms": now, "expires_ms": now + 60000}]})
                    self.assertEqual(result["transaction_status"], "accepted")
                    self.assertTrue(any(row["id"] == "ci-key" and row["status"] == "executed"
                                        for row in result["rawacks"]))
                    self.assertEqual(errors, [])
                    browser = env._browser
                self.assertFalse(browser.is_connected())


class GymTests(unittest.TestCase):
    def test_gym_checker_and_complete_episode(self):
        with RhythmEnv() as env:
            check_env(env)
            observation, _ = env.reset(seed=1)
            env.action_space.seed(1)
            self.assertTrue(env.observation_space.contains(observation))
            for _ in range(5000):
                observation, _, terminated, truncated, _ = env.step(env.action_space.sample())
                self.assertTrue(env.observation_space.contains(observation))
                if terminated or truncated:
                    break
            self.assertTrue(terminated or truncated)
