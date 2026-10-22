"""Long-lived registered command routing contracts owned by the root CLI."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from runtime.cli import main


class GameRoutingTests(unittest.TestCase):
    def test_game_routes_preserve_arguments_and_exit_status(self):
        for game, commands, canonical in (
            ("asterix", ("simulate", "eval"), "asterix"),
            ("touhou", ("simulate", "eval", "profile"), "touhou"),
            ("rhythm", ("simulate", "eval", "profile"), "rhythm"),
            ("pcba", ("simulate", "eval", "report", "demo", "realtime-smoke", "view", "latency", "pipeline", "loop-demo", "export", "showcase", "figures", "clock-preflight"), "pcba"),
            ("pingpong", ("simulate", "eval", "report"), "tabletennis"),
            ("tabletennis", ("simulate", "eval", "report"), "tabletennis"),
            ("badminton", ("simulate", "eval", "preflight", "audit", "report", "diagnose", "profile"), "badminton"),
            ("racing", ("simulate", "eval", "profile", "preflight", "record", "budget"), "racing"),
        ):
            for command in commands:
                with self.subTest(game=game, command=command), \
                     patch.object(sys, "argv", ["sol", command, game, "--help"]), \
                     patch("runtime.cli.envs.launch", side_effect=SystemExit(7)) as call:
                    with self.assertRaises(SystemExit) as stopped:
                        main()
                    self.assertEqual(stopped.exception.code, 7)
                    self.assertEqual(call.call_args.args[1:], (canonical, [command, "--help"]))

    def test_registry_and_setup_only_errors_need_no_site_packages(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-S', '-m', 'runtime.cli', 'env', 'list'],
                                cwd=root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({json.loads(line)['game'] for line in result.stdout.splitlines()},
                         {'asterix', 'touhou', 'rhythm', 'pcba', 'racing', 'badminton', 'tabletennis', 'pvz', 'vera20k'})
        for game in ('pvz', 'vera20k'):
            result = subprocess.run([sys.executable, '-S', '-m', 'runtime.cli', 'simulate', game],
                                    cwd=root, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(f'Environment {game} does not support simulate', result.stderr)

    def test_doctor_uses_each_games_interpreter_and_collects_failures(self):
        for extra in ([], ["--auth", "--browser-executable", "/browser"]):
            with patch.object(sys, "argv", ["sol", "doctor", "--game", "touhou", *extra]), \
                 patch("runtime.cli.envs.launch") as launch:
                main()
                self.assertEqual(launch.call_args.args[1:], ("touhou", ["doctor", *extra]))
        with patch.object(sys, "argv", ["sol", "doctor", "--auth", "--browser-executable", "/browser"]), \
             patch("runtime.cli.envs.check", side_effect=[RuntimeError("needs setup"), {}, {}]) as check:
            with self.assertRaises(SystemExit) as stopped:
                main()
            self.assertEqual(stopped.exception.code, 1)
            self.assertEqual([call.args[1:] for call in check.call_args_list], [
                ('asterix', ['--auth', '--browser-executable', '/browser']),
                ('touhou', ['--browser-executable', '/browser']),
                ('rhythm', ['--browser-executable', '/browser']),
            ])


if __name__ == "__main__":
    unittest.main()
