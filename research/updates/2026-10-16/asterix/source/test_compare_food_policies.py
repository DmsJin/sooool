"""Offline scheduling acceptance, not model-quality evidence."""
from pathlib import Path
from types import SimpleNamespace
import json
import tempfile
import threading
import unittest
from unittest.mock import patch
import compare_food_policies as comparison


class ComparisonTests(unittest.TestCase):
    def fixture(self,root):
        source=root/'source';source.mkdir()
        for name in ('subscription_client.py','subscription_quota.py'):
            (source/name).write_text('# Public test source\n')
        profile=root/'profile.json';profile.write_text(json.dumps({'capture_to_complete_seconds':[1.,2.]}))
        strategies=[]
        for name in ('baseline','candidate'):
            path=root/(name+'.txt');path.write_text(name+' policy');strategies.append(path)
        system=root/'system.txt';system.write_text('Minimal system')
        return SimpleNamespace(source=source,suite=root,profile=profile,minimal_system_file=system,
            output=root/'result',strategy=strategies,seeds=[2,5,6],max_frames=1200,repeats=1,
            order_seed=91,latency_seed_offset=91,quota_stop_percent=80,dry_run=False)

    def test_fresh_isolated_games_share_eight_workers_and_paired_delay_seeds(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory));seen=[];lock=threading.Lock()
            def game(cfg,seed,pool,prompt,delays):
                self.assertEqual(pool.pool._max_workers,8)
                self.assertIsNone(cfg.replay_root)
                self.assertEqual(cfg.controller,'v3')
                self.assertIn(cfg.strategy.read_text(),prompt)
                (cfg.output/f'seed-{seed}').mkdir()
                with lock:seen.append((cfg.strategy.stem,seed,cfg.latency_seed_offset,id(pool)))
                return {'seed':seed,'frames':1200,'score':0,'error':None}
            with patch.object(comparison,'run_episode',side_effect=game):comparison.main(args)
            self.assertEqual(len(seen),6)
            self.assertEqual(len({(p,s) for p,s,_,_ in seen}),6)
            self.assertEqual(len({pool for _,_,_,pool in seen}),1)
            self.assertEqual({offset for _,_,offset,_ in seen},{91})
            summary=json.loads((args.output/'summary.json').read_text())
            self.assertEqual(summary['status'],'complete')
            self.assertEqual(len(summary['episodes']),6)
            for strategy in args.strategy:
                config=json.loads((args.output/strategy.stem/'repeat-0/config.json').read_text())
                self.assertEqual(config['strategy'],str(strategy))

    def test_partial_results_never_report_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory))
            def game(cfg,seed,*rest):
                return {'seed':seed,'frames':1200,'score':0,'error':{'type':'test failure'} if cfg.strategy.stem=='candidate' and seed==5 else None}
            with patch.object(comparison,'run_episode',side_effect=game):
                with self.assertRaises(RuntimeError):comparison.main(args)
            summary=json.loads((args.output/'summary.json').read_text())
            self.assertEqual(summary['status'],'incomplete')
            self.assertEqual(len(summary['episodes']),6)

    def test_dry_run_creates_no_result_or_model_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            args=self.fixture(Path(directory));args.dry_run=True
            with patch.object(comparison,'NativePool',side_effect=AssertionError('No inference on dry run')),patch('builtins.print'):
                comparison.main(args)
            self.assertFalse(args.output.exists())


if __name__=='__main__':unittest.main()
