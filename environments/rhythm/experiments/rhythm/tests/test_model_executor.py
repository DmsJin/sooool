"""Generic blank-page executor tests: no chart, image, audio or game fixture."""
import asyncio
import json
import unittest
from playwright.async_api import async_playwright
from experiments.rhythm.model_executor import ModelExecutor, parse_commands


def tap(id,key,at,expires):return {'id':id,'key':key,'at_ms':at,'expires_ms':expires}
def tx(version,taps=(),cancels=()):return {'version':version,'cancel_ids':list(cancels),'taps':list(taps)}

class SchemaTests(unittest.TestCase):
    def test_no_unrequested_fields_or_unbounded_schema(self):
        command=tx(0,[tap('n1','d',10,20)])
        self.assertEqual(parse_commands(json.dumps(command)),command)
        for bad in [dict(command,tempo=113),dict(command,replace_pending=1),tx(True),tx(0,[tap('n1','D',10,20)]),
                    tx(0,[tap('n1','d',float('nan'),20)]),tx(0,[tap('n1','d',30,20)]),
                    tx(0,[tap(str(i),'d',10,20)for i in range(13)]),
                    tx(0,[tap('same','d',10,20),tap('same','f',10,20)])]:
            with self.assertRaises(ValueError):parse_commands(bad)

class BrowserExecutorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pw=await async_playwright().start()
        self.browser=await self.pw.chromium.launch(headless=True)
        self.page=await self.browser.new_page()
        await self.page.evaluate('''() => {
          window.testClock=1000;Object.defineProperty(performance,'now',{value:()=>window.testClock});
          window.events=[];
          for(const kind of ['keydown','keyup'])window.addEventListener(kind,e=>events.push({kind,key:e.key,code:e.code,actual_ms:performance.now()}));
        }''')
        self.executor=await ModelExecutor(self.page).install()
    async def asyncTearDown(self):
        await self.browser.close();await self.pw.stop()
    async def advance(self,value):
        await self.page.evaluate('v=>window.testClock=v',value)
        await self.executor.drain()
    async def events(self):return await self.page.evaluate('window.events')

    async def test_model_expiry_is_only_lateness_rule_and_at_is_unchanged(self):
        await self.executor.apply(tx(0,[tap('late','d',100,2000),tap('future','f',1010,1020),tap('expire','j',1025,1030)]))
        initial=await self.executor.snapshot()
        late=[r for r in initial['rawacks']if r['status']=='executed'][0]
        self.assertEqual((late['at_ms'],late['actual_ms']),(100,1000))
        await self.advance(1015)
        await self.advance(1031)
        events=await self.events()
        self.assertEqual([(e['kind'],e['code'],e['actual_ms'])for e in events],
            [('keydown','KeyD',1000),('keyup','KeyD',1000),('keydown','KeyF',1015),('keyup','KeyF',1015)])
        state=await self.executor.snapshot(initial['cursor'])
        self.assertEqual(state['clock_ms'],1031)
        self.assertEqual([r['status']for r in state['rawacks']],['executed','expired'])
        self.assertEqual(state['rawacks'][0]['at_ms'],1010)
        self.assertEqual(state['pending'],[])

    async def test_versions_do_not_cancel_and_ids_never_retime(self):
        first=tx(3,[tap('a','d',1100,1200)])
        await self.executor.apply(first)
        await self.executor.apply(tx(4,[tap('b','d',1101,1200)]))
        self.assertEqual(len((await self.executor.snapshot())['pending']),2)
        stale=await self.executor.apply(tx(2,[tap('old','j',1100,1200)],cancels=['a']))
        self.assertEqual(stale['transaction_status'],'rejected')
        idem=await self.executor.apply(first)
        self.assertEqual(idem['transaction_status'],'idempotent_retry')
        conflict=await self.executor.apply(tx(4,[tap('b','f',1101,1200)]))
        self.assertEqual(conflict['transaction_status'],'rejected')
        await self.executor.apply(tx(5,[tap('a','d',1150,1200)]))
        state=await self.executor.snapshot()
        self.assertEqual(next(r for r in state['pending']if r['id']=='a')['at_ms'],1100)
        await self.advance(1100);await self.advance(1101)
        # No implicit same-key refractory period: two one-ms-separated taps execute.
        self.assertEqual(len(await self.events()),4)
        await self.executor.apply(tx(6,[tap('c','k',1150,1200)]))
        await self.executor.apply(tx(7,cancels=['c']))
        await self.advance(1160)
        self.assertEqual(len(await self.events()),4)
        self.assertIn('cancelled',[r['status']for r in (await self.executor.snapshot())['rawacks']])

    async def test_replace_pending_occurs_only_on_explicit_model_flag(self):
        await self.executor.apply(tx(0,[tap('old_a','d',1100,1400)]))
        await self.executor.apply(tx(1,[tap('old_b','f',1200,1400)]))
        self.assertEqual(len((await self.executor.snapshot())['pending']),2)
        replacement=dict(tx(2,[tap('new','k',1300,1400),tap('wrong_model_time','j',900,2000)]),replace_pending=True)
        result=await self.executor.apply(replacement)
        self.assertEqual([r['id']for r in result['pending']],['new'])
        cleared=[r for r in result['rawacks']if r.get('reason')=='replace_pending']
        self.assertEqual({r['id']for r in cleared},{'old_a','old_b'})
        wrong=next(r for r in result['rawacks']if r['id']=='wrong_model_time' and r['status']=='executed')
        # Even a deliberately wrong model time is not inferred or repaired.
        self.assertEqual((wrong['at_ms'],wrong['actual_ms']),(900,1000))
        await self.advance(1300)
        self.assertEqual([e['code']for e in await self.events() if e['kind']=='keydown'],['KeyJ','KeyK'])
        self.assertEqual((await self.executor.snapshot())['pending'],[])
        retry=await self.executor.apply(replacement)
        self.assertEqual(retry['transaction_status'],'idempotent_retry')
        self.assertEqual(len(await self.events()),4)

    async def test_out_of_order_additions_survive_newer_empty_plan(self):
        await self.executor.apply(tx(9))
        added=await self.executor.apply(tx(3,[tap('older','d',1100,1400)]))
        self.assertEqual(added['transaction_status'],'accepted')
        self.assertEqual(added['version'],9)
        self.assertEqual(added['pending'][0]['admitted_version'],3)
        admission=next(r for r in added['rawacks'] if r.get('id')=='older' and r['status']=='admitted')
        self.assertEqual(admission['admitted_version'],3)
        self.assertEqual(admission['at_ms'],1100)
        replacement=dict(tx(4,[tap('replacement','f',1200,1400)]),replace_pending=True)
        self.assertEqual((await self.executor.apply(replacement))['transaction_status'],'rejected')
        self.assertEqual((await self.executor.apply(tx(5,cancels=['older'])))['transaction_status'],'rejected')
        # ID collision from an older addition never changes the first command.
        collision=await self.executor.apply(tx(2,[tap('older','k',1300,1400)]))
        self.assertEqual(collision['version'],9)
        self.assertEqual(collision['pending'][0]['key'],'d')
        self.assertEqual(collision['pending'][0]['at_ms'],1100)
        await self.advance(1100)
        self.assertEqual([e['code'] for e in await self.events() if e['kind']=='keydown'],['KeyD'])
        self.assertEqual((await self.executor.snapshot())['version'],9)

    async def test_explicit_replacement_retains_literal_pending_copies_only(self):
        retained=tap('keep','d',1100,1400)
        omitted=tap('omit','f',1150,1400)
        conflict=tap('conflict','j',1200,1400)
        executed=tap('done','k',900,1400)
        await self.executor.apply(tx(0,[retained,omitted,conflict,executed]))
        replacement=dict(tx(1,[dict(retained),dict(conflict,at_ms=1250),dict(executed)]),replace_pending=True)
        state=await self.executor.apply(replacement)
        self.assertEqual([r['id']for r in state['pending']],['keep'])
        self.assertEqual(state['pending'][0]['at_ms'],1100)
        self.assertTrue(any(r['id']=='conflict' and r['status']=='rejected' for r in state['rawacks']))
        self.assertTrue(any(r['id']=='omit' and r['status']=='cancelled' for r in state['rawacks']))
        self.assertFalse(any(r['id']=='keep' and r['status']=='cancelled' for r in state['rawacks']))
        await self.advance(1300)
        downs=[e['code']for e in await self.events() if e['kind']=='keydown']
        self.assertEqual(downs,['KeyK','KeyD'])
        self.assertEqual((await self.executor.apply(replacement))['transaction_status'],'idempotent_retry')
        self.assertEqual(len(await self.events()),4)

    async def test_native_timer_runs_on_plain_page_without_drain_or_game_state(self):
        page=await self.browser.new_page()
        await page.evaluate("window.events=[];window.addEventListener('keydown',e=>events.push({key:e.key,time:performance.now()}))")
        executor=await ModelExecutor(page).install()
        now=(await executor.snapshot())['clock_ms']
        await executor.apply(tx(0,[tap('native','k',now+80,now+1000)]))
        await page.wait_for_function('window.events.length===1',polling=10,timeout=1500)
        receipt=next(r for r in (await executor.snapshot())['rawacks'] if r['status']=='executed')
        self.assertEqual(receipt['at_ms'],now+80)
        self.assertGreaterEqual(receipt['actual_ms'],now+80)
        self.assertLessEqual(receipt['actual_ms'],now+1000)
        self.assertEqual((await page.evaluate('window.events'))[0]['key'],'k')
        await page.close()

    async def test_validation_is_atomic_and_model_expiry_boundary_is_inclusive(self):
        bad=tx(0,[tap('valid','d',1000,1000),tap('invalid','x',1000,1001)])
        with self.assertRaises(Exception):await self.page.evaluate('t=>window.__modelExecutor.submit(t)',bad)
        self.assertEqual((await self.executor.snapshot())['version'],-1)
        await self.executor.apply(tx(0,[tap('boundary','d',1000,1000),tap('already_expired','f',900,999)]))
        self.assertEqual(len(await self.events()),2)
        receipts=(await self.executor.snapshot())['rawacks']
        self.assertIn('expired_before_admission',[r['status']for r in receipts])

if __name__=='__main__':unittest.main()
