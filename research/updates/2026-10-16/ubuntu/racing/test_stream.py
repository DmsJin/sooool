import json,pathlib,tempfile,threading,unittest
from unittest.mock import Mock
from run import API,Budget,MODEL,parse

class Stream(unittest.TestCase):
 def exercise(self,text,tail='',tier='ultrafast'):
  with tempfile.TemporaryDirectory() as d:
   budget=Budget(pathlib.Path(d)/'budget.json');api=API('fake',budget)
   identity={'model':MODEL,'service_tier':tier}
   emitted=[];seen=[]
   response={**identity,'status':'completed','usage':{'input_tokens':10,'output_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':text+tail}]}]}
   def lines(**kw):
    events=[{'type':'response.created','response':identity}]+[{'type':'response.output_text.delta','delta':c} for c in text]
    for e in events:yield b'data: '+json.dumps(e).encode()
    seen.append(len(emitted))
    self.assertTrue(json.loads(budget.path.read_text())['reserved'])
    if tail:yield b'data: '+json.dumps({'type':'response.output_text.delta','delta':tail}).encode()
    yield b'data: '+json.dumps({'type':'response.completed','response':response}).encode()
   http=Mock();http.status_code=200;http.iter_lines=lines;http.__enter__=Mock(return_value=http);http.__exit__=Mock(return_value=False);api.http.post=Mock(return_value=http)
   error=None
   try:answer,meta=api.act('test',[],pathlib.Path(d)/'call',on_ready=lambda *x:emitted.append(x),validator=parse)
   except RuntimeError as e:error=e;meta=None
   self.assertFalse(json.loads(budget.path.read_text())['reserved'])
   api.close();return emitted,seen,error,meta
 def test_action_published_before_completion_and_usage(self):
  emitted,seen,error,meta=self.exercise('[[2,0.1,0.2]]')
  self.assertIsNone(error);self.assertEqual(seen,[1]);self.assertEqual(len(emitted),1)
  self.assertLess(meta['published_seconds'],meta['response_completed_seconds'])
 def test_bounds_and_incomplete_never_publish(self):
  for text in ['[[5,0,0.2]]','[[2,0,0.2]']:
   emitted,seen,error,meta=self.exercise(text);self.assertEqual(emitted,[])
 def test_trailing_change_invalidates_trial(self):
  emitted,seen,error,meta=self.exercise('[[2,0,0.2]]',' junk')
  self.assertIsNotNone(error);self.assertEqual(len(emitted),1)
 def test_wrong_tier_never_publishes(self):
  emitted,seen,error,meta=self.exercise('[[2,0,0.2]]',tier='default')
  self.assertIsNotNone(error);self.assertEqual(emitted,[])
if __name__=='__main__':unittest.main()
