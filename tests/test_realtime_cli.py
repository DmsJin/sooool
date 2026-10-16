import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from runtime import cli

class RealtimeCLI(unittest.TestCase):
    def test_paid_asterix_requires_budget_before_transport(self):
        with patch.object(sys,'argv',['sol','eval','asterix','--provider','api']),patch.object(cli,'asterix') as game:
            with self.assertRaises(SystemExit):cli.main()
            game.assert_not_called()

    def test_paid_asterix_uses_explicit_wall_duration_and_api_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'run'
            def freeze(game,recipe,path,mode):
                path.mkdir()
                (path/'manifest.json').write_text(json.dumps({'game':game,'recipe':recipe,'mode':mode}))
            argv=['sol','eval','asterix','--provider','api','--budget-usd','5','--wall-seconds','60','--output',str(out)]
            with patch.object(sys,'argv',argv),patch.object(cli,'freeze',side_effect=freeze),patch.object(cli,'asterix',return_value={}) as game:
                cli.main()
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
                with patch.object(sys,'argv',['sol','eval',game,'--output',str(out),*extra]),patch.object(cli,'freeze',side_effect=freeze),patch.object(cli,'asterix',return_value={}) as ast,patch.object(cli,'touhou_realtime',return_value={}) as tou:
                    cli.main()
                    selected,other=(ast,tou) if game=='asterix' else (tou,ast)
                    selected.assert_called_once();other.assert_not_called()
                    self.assertEqual(json.loads((out/'manifest.json').read_text())['mode'],mode)
                    recipe=selected.call_args.args[0]
                    self.assertEqual(recipe,json.loads((cli.ROOT/'recipes'/('asterix.json' if game=='asterix' else 'touhou-realtime.json')).read_text()))

    def test_record_dispatch_keeps_assessments_and_registry_separate(self):
        for game in ['asterix','touhou']:
            with self.subTest(game=game),tempfile.TemporaryDirectory() as d:
                run=Path(d)
                (run/'manifest.json').write_text(json.dumps({'game':game}))
                extra=['--decision','diagnostic','--note','Review'] if game=='asterix' else []
                with patch.object(sys,'argv',['sol','record',str(run),*extra]),patch('runtime.evaluation.assess',return_value={}) as assess,patch('runtime.touhou_records.append_record',return_value=True) as append:
                    cli.main()
                    selected,other=(assess,append) if game=='asterix' else (append,assess)
                    selected.assert_called_once();other.assert_not_called()

    def test_budget_required_and_invalid_budget_rejected_before_run(self):
        for extra in ([],['--budget-usd','NaN'],['--budget-usd','-1']):
            with patch.object(sys,'argv',['sol','eval','touhou',*extra]),patch.object(cli,'touhou_realtime') as live:
                with self.assertRaises(SystemExit):cli.main()
                live.assert_not_called()
    def test_simulate_rejects_api_recipe_before_any_provider(self):
        with patch.object(sys,'argv',['sol','simulate','touhou','--recipe',str(cli.ROOT/'recipes/touhou-realtime.json')]),patch.object(cli,'touhou') as sim,patch.object(cli,'touhou_realtime') as live:
            with self.assertRaises(SystemExit):cli.main()
            sim.assert_not_called();live.assert_not_called()

    def test_profile_console_success_returns_none_not_an_exit_error(self):
        with patch.object(sys,'argv',['sol','profile','touhou','--episode','unused','--budget-usd','1']),patch('runtime.touhou_profile.profile',return_value={'complete':True}) as run:
            self.assertIsNone(cli.main())
            run.assert_called_once()
