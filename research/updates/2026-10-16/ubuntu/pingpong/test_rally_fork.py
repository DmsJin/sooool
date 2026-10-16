"""Public prefix ordering and branch score exclusion; no native world or requests."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rally_fork import prefix_before,replay_prefix
import run_round


class ForkTests(unittest.TestCase):
    def test_same_tick_commands_before_target_only(self):
        rows=[{'ev':'cmd','k':1,'seat':'A','cmd':{'type':'move'}},
              {'ev':'resume','k':2},
              {'ev':'cmd','k':3,'seat':'A','cmd':{'type':'toss'}},
              {'ev':'model_issued','k':3,'seq':7},
              {'ev':'cmd','k':3,'seat':'A','cmd':{'type':'future'}}]
        prefix,target=prefix_before(rows,7);calls=[];logs=[]
        class Match:
            k=0
            def step(self):self.k+=1
            def apply(self,seat,cmd):calls.append((self.k,seat,cmd))
            def resume(self):calls.append((self.k,'resume'))
        m=Match();ep=SimpleNamespace(write=lambda ev,**kw:logs.append((ev,kw)))
        replay_prefix(m,prefix,target,ep)
        self.assertEqual(m.k,3)
        self.assertEqual(calls,[(1,'A',{'type':'move'}),(2,'resume'),(3,'A',{'type':'toss'})])
        self.assertEqual([ev for ev,kw in logs],['cmd','resume','cmd'])
        self.assertNotIn('future',str(calls))

    def test_terminal_branch_never_counts_as_complete_win(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'plan.json'
            p.write_text(json.dumps({'profile':'unused','jobs':[{'name':'branch','seed':151,'variant':'geometry_chunk',
                'fork_from':'source','fork_seq':7}]}))
            def launch(cmd,**kwargs):
                self.assertEqual(cmd[cmd.index('--fork-seq')+1],'7')
                out=Path(cmd[cmd.index('--output')+1]);out.mkdir()
                (out/'summary.json').write_text(json.dumps({'finished':True,'branched':True,'winner':'A','failure':None}))
                return SimpleNamespace(pid=123,wait=lambda:0)
            with patch.object(run_round.subprocess,'Popen',side_effect=launch):
                run_round.run(SimpleNamespace(plan=p,output=root/'out',python='unused'))
            result=json.loads((root/'out/results.json').read_text())
            self.assertEqual(result['completed'],0)
            self.assertEqual(result['wins'],0)
            self.assertIsNone(result['jobs']['branch']['summary']['winner'])
            self.assertFalse(result['jobs']['branch']['include_in_scores'])


if __name__=='__main__':unittest.main()
