"""Keep PingPong aliases and upstream Badminton commands on their owning runners."""
import sys
import unittest
from unittest.mock import patch

from runtime.cli import main


class GameRoutingTests(unittest.TestCase):
    def test_game_routes_preserve_arguments_and_exit_status(self):
        for game, commands, canonical in (
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


if __name__ == "__main__":
    unittest.main()
