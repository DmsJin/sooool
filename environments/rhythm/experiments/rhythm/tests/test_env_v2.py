"""Browser executor tests; trusted chart is fixture/evaluator only, no model calls."""
import asyncio,json,unittest
from pathlib import Path
from experiments.rhythm.visual_env_v2 import VisualRhythmEnv
from experiments.rhythm.visual_env import ROOT

class V2ExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_idempotent_replace_late_grace_guard_and_exact_frame(self):
        chart=json.loads((ROOT/'dist/chart.json').read_text())['notes']
        async with VisualRhythmEnv('http://127.0.0.1:18891',virtual=True,late_grace_ms=55) as env:
            await env.start_virtual()
            initial=await env.screenshot();await asyncio.sleep(.1)
            self.assertEqual((await env.screenshot()).time_s,initial.time_s)
            first=chart[0]
            await env.schedule([{'time':first['time'],'lane':first['lane']}])
            await env.advance(first['time'])
            first_snapshot=await env.snapshot()
            self.assertEqual(len(first_snapshot['actions']),1)
            # A slow Python replace arriving after execution cannot press twice.
            await env.replace_schedule([{'time':first['time'],'lane':first['lane']}])
            self.assertEqual(len(await env.action_log()),1)
            second=chart[1]
            await env.advance(second['time']+.035)
            await env.replace_schedule([{'time':second['time'],'lane':second['lane']}])
            log=await env.action_log()
            self.assertEqual(log[-1]['status'],'executed')
            self.assertAlmostEqual(log[-1]['actual']-second['time'],.035)
            self.assertEqual((await env.evaluator())['counts']['perfect'],2)
            third=chart[2]
            await env.advance(third['time']+.100)
            await env.replace_schedule([{'time':third['time'],'lane':third['lane']}])
            self.assertEqual((await env.action_log())[-1]['status'],'expired')
            fourth=chart[3]
            await env.schedule([{'time':fourth['time'],'lane':fourth['lane']}])
            await env.advance(fourth['time']-.025)
            await env.replace_schedule([{'time':fourth['time']+.020,'lane':fourth['lane']}],commit_guard_ms=50)
            await env.advance(fourth['time']+.1)
            fourth_events=[a for a in await env.action_log() if a['lane']==fourth['lane']]
            self.assertEqual(len(fourth_events),1)
            self.assertAlmostEqual(fourth_events[0]['time'],fourth['time'])
            incremental=await env.snapshot(first_snapshot['cursor'])
            self.assertEqual(len(incremental['actions']),3)
            self.assertEqual(incremental['cursor'],4)
            self.assertAlmostEqual((await env.screenshot()).time_s,fourth['time']+.1)

if __name__=='__main__':unittest.main()
