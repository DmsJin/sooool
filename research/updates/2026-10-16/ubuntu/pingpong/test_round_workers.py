"""Offline launch-boundary checks; no subprocesses or subscription requests."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import run_round
import speed_screen_intra


class RoundWorkerTests(unittest.TestCase):
    def test_invalid_workers_never_launch_or_create_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for value in (0,9,-1,True,False,1.5,'3',None):
                plan=root/'plan.json';plan.write_text(json.dumps({'workers_per_episode':value}))
                args=SimpleNamespace(plan=plan,output=root/'out',python='unused')
                with patch.object(run_round.subprocess,'Popen') as launch:
                    with self.assertRaises(ValueError):run_round.run(args)
                    launch.assert_not_called()
                self.assertFalse(args.output.exists())

    def test_worker_forwarding_and_screen_excludes_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for value in (None,3,8):
                plan={'profile':'unused','jobs':[{'name':'fixture','seed':151,'variant':'geometry_chunk'}],
                      'screen_points':2,'screen_decisions':30}
                if value is not None:plan['workers_per_episode']=value
                path=root/'plan.json';path.write_text(json.dumps(plan));output=root/str(value)
                def fake_launch(cmd,**kwargs):
                    self.assertEqual(cmd[cmd.index('--workers')+1],str(value or 1))
                    self.assertNotIn('--capacity',cmd)
                    self.assertEqual(cmd[cmd.index('--screen-decisions')+1],'30')
                    out=Path(cmd[cmd.index('--output')+1]);out.mkdir()
                    (out/'summary.json').write_text(json.dumps({'finished':False,'screened':True,'winner':None,'failure':None}))
                    return SimpleNamespace(pid=123,wait=lambda:0)
                with patch.object(run_round.subprocess,'Popen',side_effect=fake_launch):
                    run_round.run(SimpleNamespace(plan=path,output=output,python='unused'))
                result=json.loads((output/'results.json').read_text())
                self.assertEqual(result['wins'],0)
                self.assertEqual(result['completed'],0)
                self.assertFalse(result['jobs']['fixture']['include_in_scores'])

    def test_intra_screen_stage_plans_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);external=root/'external.json';external.write_text('{}');plans=[]
            def fake_call(cmd,**kwargs):
                plan=json.loads(Path(cmd[cmd.index('--plan')+1]).read_text());plans.append(plan)
                out=Path(cmd[cmd.index('--output')+1]);out.mkdir()
                (out/'results.json').write_text(json.dumps({'jobs':{j['name']:{'status':'screened'} for j in plan['jobs']}}))
                return 0
            with patch('freeze.capture',return_value={}),patch.object(speed_screen_intra.subprocess,'call',side_effect=fake_call):
                speed_screen_intra.run(SimpleNamespace(output=root/'screen',external_manifest=external,profile=root/'unused'))
            self.assertEqual([p['parallel_episodes'] for p in plans],[4,8])
            self.assertEqual([p['gap_s'] for p in plans],[.15,.1])
            self.assertNotEqual(plans[0]['freeze_manifest'],plans[1]['freeze_manifest'])
            for p in plans:
                self.assertEqual(p['workers_per_episode'],3)
                self.assertEqual(p['screen_decisions'],30)
                self.assertEqual(p['screen_points'],2)
                self.assertNotIn('capacity',p)
                self.assertEqual({j['variant'] for j in p['jobs']},{'geometry_stable_early_fast_feedback_executor_chunk','geometry_stable_early_fast_feedback_executor_rallywatch_chunk'})


if __name__=='__main__':unittest.main()
