import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from runtime import cli

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "environments/asterix"))
import simulate_5x


class DefaultAsterix(unittest.TestCase):
    def test_default_freeze_and_runner_load_selected_prompt_and_system(self):
        recipe = json.loads((ROOT / "recipes/asterix.json").read_text())
        metadata = json.loads((ROOT / "policies/asterix/v28/policy.json").read_text())
        self.assertEqual(recipe["policy"], "v28-hop3")
        self.assertEqual(recipe, json.loads((ROOT / "recipes/asterix-v28.json").read_text()))
        self.assertEqual(sorted(p.name for p in (ROOT / "policies/asterix").iterdir()), ["v28"])

        def finish_without_model(args):
            self.assertEqual(args.strategy, ROOT / "policies/asterix/v28/prompt.txt")
            self.assertEqual(args.minimal_system_file, ROOT / "policies/asterix/v28/system.txt")
            self.assertEqual(hashlib.sha256(args.strategy.read_bytes()).hexdigest(), metadata["prompt_sha256"])
            self.assertEqual(args.controller, "v3")
            self.assertEqual(args.seeds, [6])
            self.assertEqual(args.max_frames, 1200)
            args.output.mkdir(parents=True)
            (args.output / "summary.json").write_text('{"status":"transport_fixture"}')

        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary) / "episode"
            cli.freeze("asterix", recipe, out)
            frozen = json.loads((out / "manifest.json").read_text())
            self.assertEqual(frozen["recipe"]["policy"], "v28-hop3")
            self.assertEqual(
                frozen["source_sha256"]["policies/asterix/v28/prompt.txt"], metadata["prompt_sha256"]
            )
            with patch.object(simulate_5x, "NativePool"), patch.object(
                simulate_5x, "run", side_effect=finish_without_model
            ), patch("runtime.subscription.SubscriptionClient", side_effect=AssertionError("No model calls")):
                cli.asterix(recipe, out, SimpleNamespace(seed=6, duration=20))
