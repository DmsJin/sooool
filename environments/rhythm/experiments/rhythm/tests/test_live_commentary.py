"""Real-time public commentary must never gate an already complete action."""
import asyncio,json,tempfile,unittest
from experiments.rhythm.tests.test_streaming_actions import StreamingActionsTests,Client,event,response,ANSWER
from experiments.rhythm.model_commentary import complete,prompt
from experiments.rhythm.model_compact_policy import parse

class LiveCommentaryTests(unittest.IsolatedAsyncioTestCase):
 make_provider=StreamingActionsTests.make_provider
 async def test_action_then_comment_before_terminal(self):
  with tempfile.TemporaryDirectory() as tmp:
   action_ready,comment_ready,allow_comment,terminal=[asyncio.Event() for _ in range(4)]
   seen=[];full=ANSWER+'\n'+json.dumps({'comment':'D 轨音符接近，安排下一次击打。'},ensure_ascii=False)
   async def lines():
    yield event('response.created',response=response())
    yield event('response.output_text.delta',delta=ANSWER)
    await allow_comment.wait()
    for char in full[len(ANSWER):]:yield event('response.output_text.delta',delta=char)
    await terminal.wait()
    yield event('response.completed',response=response(full))
   async def act(text,timing):seen.append(('action',text));action_ready.set()
   async def comment(text,timing):seen.append(('comment',text));comment_ready.set()
   provider=self.make_provider(tmp,Client(lines))
   task=asyncio.create_task(provider.act('p',[],on_action=act,action_validator=parse,on_commentary=comment,live_commentary=True))
   try:
    await asyncio.wait_for(action_ready.wait(),2)
    self.assertEqual(seen,[('action',ANSWER)]);self.assertFalse(task.done())
    allow_comment.set();await asyncio.wait_for(comment_ready.wait(),2)
    self.assertFalse(task.done());terminal.set()
    answer,meta=await task
    self.assertEqual(answer,ANSWER);self.assertEqual(meta['raw_output'],full)
    self.assertEqual(len(seen),2);self.assertLess(meta['action_ready_s'],meta['commentary_ready_s'])
   finally:
    allow_comment.set();terminal.set();await asyncio.gather(task,return_exceptions=True);await provider.close()

 async def test_malformed_tail_does_not_resend_or_lose_accounting(self):
  for tail in ('','\n{"comment":"'+('字'*81)+'"}','\nnull','\n{"comment":"好"}\n'+ANSWER):
   with self.subTest(tail=tail),tempfile.TemporaryDirectory() as tmp:
    full=ANSWER+tail;seen=[]
    async def lines():
     yield event('response.created',response=response())
     yield event('response.output_text.delta',delta=ANSWER)
     yield event('response.output_text.delta',delta=tail)
     yield event('response.completed',response=response(full))
    async def act(*args):seen.append(args)
    client=Client(lines);provider=self.make_provider(tmp,client)
    try:
     with self.assertRaises((ValueError,TypeError)):
      await provider.act('p',[],on_action=act,action_validator=parse,live_commentary=True)
     self.assertEqual(len(seen),1);self.assertEqual(client.calls,1)
     records=[v for k,v in provider.ledger.snapshot()['requests'].items() if k!='prior']
     self.assertEqual(records[0]['state'],'settled')
    finally:await provider.close()

 def test_separator_and_extra_record(self):
  self.assertEqual(complete(ANSWER+'\n{"comment":"好"}'),(ANSWER,'好'))
  for tail in (' {"comment":"好"}','\n[]','\n{"comment":"好","a":[]}'):
   with self.assertRaises(ValueError):complete(ANSWER+tail)

 def test_english_instruction_preserves_action_first_protocol(self):
  text=prompt("Original action policy",language="en")
  self.assertIn("Original action policy",text)
  self.assertIn("brief English public explanation",text)
  self.assertIn("FIRST: the unchanged requested action JSON",text)
  with self.assertRaises(ValueError):prompt("policy",language="fr")
