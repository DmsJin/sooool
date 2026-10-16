"""Offline execution-clock boundaries for resumed, already-accepted chunks."""
import unittest
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import run_round
from resume_timing import terminal_step,execution_cost,retry_delay


class ResumeTimingTests(unittest.TestCase):
    def cost(self,step,blocks=None,actual=.27,cutoff=92,terminal=1708,seq=88):
        return execution_cost(step,seq,cutoff,terminal,blocks or {},actual,10,.01)

    def test_cached_choice_new_tail_effect_uses_fresh_cost(self):
        # The old choice was cached, but its accepted toss is first delivered
        # after the original run stopped. No historical wall cost exists.
        elapsed,replayed,provenance=self.cost(1726)
        self.assertEqual(elapsed,.27);self.assertIsNone(replayed)
        self.assertEqual(provenance['source_terminal_step'],1708)
        self.assertEqual(provenance['effect_step'],1726)
        self.assertEqual(provenance['cost_source'],'fresh measured lowering/apply')

    def test_missing_history_at_or_before_original_terminal_fails(self):
        for step in (1707,1708):
            with self.assertRaisesRegex(ValueError,'Missing cached execution block'):self.cost(step)

    def test_recorded_history_cost_and_ticks_remain_strict(self):
        row={'k':1696,'seq':88,'until':1699,'elapsed_wall_s':.222}
        self.assertEqual(self.cost(1696,{(1696,88):row}),(.222,.27,None))
        for change in ({'until':1698},{'elapsed_wall_s':float('nan')},
                       {'elapsed_wall_s':-1},{'elapsed_wall_s':True},{'seq':87}):
            with self.assertRaisesRegex(ValueError,'Invalid cached execution block'):
                self.cost(1696,{(1696,88):{**row,**change}})

    def test_fresh_decisions_and_no_resume_keep_original_cost_fields(self):
        self.assertEqual(self.cost(1726,seq=92),(.27,None,None))
        self.assertEqual(self.cost(10,cutoff=0,terminal=None,seq=0),(.27,None,None))

    def test_terminal_requires_matching_summary_and_final_end(self):
        rows=[{'ev':'effect','k':1696},{'ev':'end','k':1708}]
        self.assertEqual(terminal_step({'k':1708},rows),1708)
        for summary,history in (({'k':1709},rows),({'k':1708.},rows),
                                ({'k':1708},rows[:-1]),({'k':1708},rows+[{'ev':'effect','k':1709}]),
                                ({'k':1708},[{'ev':'effect','k':1726},rows[-1]])):
            with self.assertRaises(ValueError):terminal_step(summary,history)

    def test_timeout_recovery_is_explicit_bounded_and_distinct_from_capacity(self):
        summary={'failure':'RuntimeError: Subscription worker exited; inspect native stderr; no paid fallback'}
        stderr='Traceback\nTimeoutError: codex did not finish this request\n'
        self.assertEqual(retry_delay(stderr,summary,0),2)
        self.assertEqual(retry_delay(stderr,summary,1),2)
        self.assertIsNone(retry_delay(stderr,summary,2))
        self.assertIsNone(retry_delay(stderr,{'failure':'ValueError: missing history'},0))
        self.assertIsNone(retry_delay('worker exited',summary,0))
        self.assertEqual(retry_delay('serverOverloaded',summary,0),60)
        self.assertEqual(retry_delay('Selected model is at capacity',summary,0),60)
        for fault in ('quota exhausted','model mismatch','native replay mismatch','numerical error',
                      'non-finite state','NaN in native state','Missing cached execution block'):
            self.assertIsNone(retry_delay(stderr+'\n'+fault,summary,0))
            self.assertIsNone(retry_delay('serverOverloaded\n'+fault,summary,0))

    def test_round_retries_same_job_prefix_only_and_preserves_failed_attempts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);plan=root/'plan.json';output=root/'round';commands=[]
            plan.write_text(json.dumps({'profile':'frozen-profile','jobs':[
                {'name':'fixture','seed':139,'variant':'geometry_executor_marginserve_chunk'}]}))
            def launch(cmd,**kwargs):
                commands.append(cmd);out=Path(cmd[cmd.index('--output')+1]);out.mkdir()
                self.assertEqual(cmd[cmd.index('--seed')+1],'139')
                self.assertEqual(cmd[cmd.index('--profile')+1],'frozen-profile')
                self.assertEqual(cmd[cmd.index('--variant')+1],'geometry_executor_marginserve_chunk')
                attempt=len(commands)-1
                if attempt:
                    self.assertEqual(cmd[cmd.index('--resume-from')+1],str(out.parent/f'attempt_{attempt-1:02d}'))
                else:self.assertNotIn('--resume-from',cmd)
                (out/'summary.json').write_text(json.dumps({'finished':False,'failure':
                    'RuntimeError: Subscription worker exited; inspect native stderr; no paid fallback'}))
                (out/'native_0.stderr').write_text('TimeoutError: codex did not finish this request\n')
                return SimpleNamespace(pid=123,wait=lambda:1)
            with patch.object(run_round.subprocess,'Popen',side_effect=launch),patch.object(run_round.time,'sleep') as sleep:
                run_round.run(SimpleNamespace(plan=plan,output=output,python='unused'))
            self.assertEqual(len(commands),3)
            self.assertEqual([call.args for call in sleep.call_args_list],[(2,),(2,)])
            report=json.loads((output/'results.json').read_text());job=report['jobs']['fixture']
            self.assertEqual(job['status'],'incomplete');self.assertFalse(job['include_in_scores'])
            self.assertEqual(len(job['attempts']),3)
            self.assertEqual(report['wins'],0);self.assertEqual(report['completed'],0)
            self.assertTrue(job['attempts'][0]['recovery']['same_seed_policy_profile'])


if __name__=='__main__':unittest.main()
