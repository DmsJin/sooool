import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from runtime import cli

class RealtimeCLI(unittest.TestCase):
    def test_budget_required_and_invalid_budget_rejected_before_run(self):
        for extra in ([],['--budget-usd','NaN'],['--budget-usd','-1']):
            with patch.object(sys,'argv',['sol','eval','touhou',*extra]),patch.object(cli,'touhou_realtime') as live:
                with self.assertRaises(SystemExit):cli.main()
                live.assert_not_called()
    def test_simulate_rejects_api_recipe_before_any_provider(self):
        with patch.object(sys,'argv',['sol','simulate','touhou','--recipe',str(cli.ROOT/'recipes/touhou-realtime.json')]),patch.object(cli,'touhou') as sim,patch.object(cli,'touhou_realtime') as live:
            with self.assertRaises(SystemExit):cli.main()
            sim.assert_not_called();live.assert_not_called()
