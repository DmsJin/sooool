"""Long-lived provider, budget and provenance contracts owned by experiment entrypoints."""
import json
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from runtime import cli, experiment, run_support
from runtime.options import credential
from environments.asterix import cli as asterix_cli
from environments.touhou import cli as touhou_cli


def run_selected():
    return {'asterix': asterix_cli, 'touhou': touhou_cli}[sys.argv[2]].main([sys.argv[1], *sys.argv[3:]])

class RealtimeCLI(unittest.TestCase):
    def test_credentials_use_process_memory_and_noninteractive_missing_keys_fail(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-process-key'}), patch('getpass.getpass') as prompt:
            self.assertEqual(credential(), 'fixture-process-key')
            prompt.assert_not_called()
        with patch.dict(os.environ, {}, clear=True), patch.object(sys, 'stdin', io.StringIO()), patch('getpass.getpass') as prompt:
            with self.assertRaisesRegex(ValueError, 'Set OPENAI_API_KEY'):
                credential()
            prompt.assert_not_called()

    def test_paid_asterix_requires_budget_before_transport(self):
        with patch.object(sys,'argv',['sol','eval','asterix','--provider','api']),patch.object(asterix_cli,'asterix') as game:
            with self.assertRaises(SystemExit):run_selected()
            game.assert_not_called()

    def test_subscription_asterix_rejects_api_only_call_limit(self):
        with patch.object(sys,'argv',['sol','eval','asterix','--max-calls','1']), patch.object(asterix_cli,'asterix') as game:
            with self.assertRaises(SystemExit):
                run_selected()
            game.assert_not_called()

    def test_paid_asterix_uses_explicit_wall_duration_and_api_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'run'
            def freeze(game,recipe,path,mode):
                path.mkdir()
                (path/'manifest.json').write_text(json.dumps({'game':game,'recipe':recipe,'mode':mode}))
            argv=['sol','eval','asterix','--provider','api','--budget-usd','5','--wall-seconds','60','--output',str(out)]
            with patch.object(sys,'argv',argv),patch.object(experiment,'freeze',side_effect=freeze),patch.object(asterix_cli,'asterix',return_value={}) as game:
                run_selected()
                self.assertEqual(game.call_args.args[2].duration,12)
                manifest=json.loads((out/'manifest.json').read_text())
                self.assertEqual(manifest['mode'],'realtime_api')
                self.assertEqual(manifest['recipe']['provider'],'openai_api')

    def test_eval_dispatch_preserves_each_games_provider_and_recipe(self):
        for game,extra,mode in [('asterix',[],'real_time_subscription'),('touhou',['--budget-usd','1'],'realtime_api')]:
            with self.subTest(game=game),tempfile.TemporaryDirectory() as d:
                out=Path(d)/'run'
                def freeze(g,recipe,path,mode):
                    path.mkdir()
                    (path/'manifest.json').write_text(json.dumps({'game':g,'recipe':recipe,'mode':mode}))
                with patch.object(sys,'argv',['sol','eval',game,'--output',str(out),*extra]),patch.object(experiment,'freeze',side_effect=freeze),patch.object(asterix_cli,'asterix',return_value={}) as ast,patch.object(touhou_cli,'touhou_realtime',return_value={}) as tou:
                    run_selected()
                    selected,other=(ast,tou) if game=='asterix' else (tou,ast)
                    selected.assert_called_once();other.assert_not_called()
                    self.assertEqual(json.loads((out/'manifest.json').read_text())['mode'],mode)
                    recipe=selected.call_args.args[0]
                    self.assertEqual(recipe,json.loads((cli.ROOT/'recipes'/('asterix.json' if game=='asterix' else 'touhou-realtime.json')).read_text()))

    def test_budget_required_and_invalid_budget_rejected_before_run(self):
        for extra in ([],['--budget-usd','NaN'],['--budget-usd','-1']):
            with patch.object(sys,'argv',['sol','eval','touhou',*extra]),patch.object(touhou_cli,'touhou_realtime') as live:
                with self.assertRaises(SystemExit):run_selected()
                live.assert_not_called()
    def test_simulate_rejects_api_recipe_before_any_provider(self):
        with patch.object(sys,'argv',['sol','simulate','touhou','--recipe',str(cli.ROOT/'recipes/touhou-realtime.json')]),patch.object(touhou_cli,'touhou') as sim,patch.object(touhou_cli,'touhou_realtime') as live:
            with self.assertRaises(SystemExit):run_selected()
            sim.assert_not_called();live.assert_not_called()

    def test_profile_console_success_returns_none_not_an_exit_error(self):
        with patch.object(sys,'argv',['sol','profile','touhou','--episode','unused','--budget-usd','1']),patch('runtime.touhou_profile.profile',return_value={'complete':True}) as run:
            self.assertIsNone(run_selected())
            run.assert_called_once()


class ManifestProvenance(unittest.TestCase):
    def test_api_and_subscription_runs_do_not_share_a_misleading_transport_label(self):
        cases = [
            ('realtime_api', 'paid API', 'wall clock'),
            ('serial_api_profile', 'paid API', 'no gameplay actions'),
            ('real_time_subscription', 'subscription', 'wall clock'),
            ('subscription_with_simulated_profile', 'subscription', 'virtual timing'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = {'scripts/rhythm.py': b'# game entrypoint',
                      'environments/registry.json': b'{"games": {}}'}
            for name, data in inputs.items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            with patch.object(run_support, 'ROOT', root):
                for mode, provider, clock in cases:
                    with self.subTest(mode=mode):
                        output = root/mode
                        run_support.freeze('rhythm', {}, output, mode=mode)
                        manifest = json.loads((output/'manifest.json').read_text())
                        self.assertEqual(manifest['mode'], mode)
                        for name, data in inputs.items():
                            self.assertEqual((output/'source_snapshot'/name).read_bytes(), data)
                        self.assertIn(provider, manifest['transport_adapter'])
                        self.assertIn(clock, manifest['transport_adapter'])
                        if provider == 'paid API':
                            self.assertNotIn('app-server', manifest['transport_adapter'])
