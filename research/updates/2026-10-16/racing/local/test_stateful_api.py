import json,pathlib,tempfile,unittest
from unittest.mock import Mock
from run import API,Budget,parse,MODEL
class StatefulAPI(unittest.TestCase):
 def test_complete_history_and_reasoning_are_carried_after_drain(self):
  with tempfile.TemporaryDirectory() as d:
   b=Budget(pathlib.Path(d)/'budget.json');api=API('fake',b,stateful=True);sent=[];reserves=[]
   def post(endpoint,**kw):
    sent.append(kw['json']);reserves.append(sum(r['usd'] for r in json.loads(b.path.read_text())['reserved'].values()));index=len(sent);text='[[2,0,0.5]]';identity={'model':MODEL,'service_tier':'ultrafast'};output=[{'type':'reasoning','id':f'r{index}','encrypted_content':'local-mock-opaque'},{'type':'message','role':'assistant','content':[{'type':'output_text','text':text}]}];response={**identity,'status':'completed','output':output,'usage':{'input_tokens':1000*index,'output_tokens':100}};r=Mock();r.status_code=200;r.__enter__=Mock(return_value=r);r.__exit__=Mock(return_value=False);r.iter_lines=Mock(return_value=iter([b'data: '+json.dumps(e).encode() for e in [{'type':'response.created','response':identity},{'type':'response.output_text.delta','delta':text},{'type':'response.completed','response':response}]]));return r
   api.http.post=Mock(side_effect=post)
   api.act('first',[],pathlib.Path(d)/'one',validator=parse);api.act('next',[],pathlib.Path(d)/'two',validator=parse)
   self.assertFalse(sent[0]['store']);self.assertEqual(sent[1]['include'],['reasoning.encrypted_content']);self.assertEqual(len(sent[1]['input']),4);self.assertEqual(sent[1]['input'][0]['content'][0]['text'],'first');self.assertEqual(sent[1]['input'][1]['type'],'reasoning');self.assertEqual(sent[1]['input'][-1]['content'][0]['text'],'next');self.assertGreater(reserves[1]-reserves[0],.07);self.assertEqual(api.completed_turns,2);api.close();self.assertEqual(api.history,[])
 def test_overlapping_calls_and_unbudgeted_history_are_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'budget.json';b=Budget(p);api=API('fake',b,stateful=True);api.http.post=Mock();api.state_lock.acquire()
   try:
    with self.assertRaisesRegex(RuntimeError,'overlapping'):api.act('x',[],pathlib.Path(d)/'one')
   finally:api.state_lock.release()
   p.write_text(json.dumps({'limit_usd':30,'charged_upper_usd':29.5,'reserved':{},'stages':{}}));api.previous_input_upper=50000
   with self.assertRaisesRegex(RuntimeError,'budget admission'):api.act('x',[],pathlib.Path(d)/'two')
   api.http.post.assert_not_called();api.close()
if __name__=='__main__':unittest.main()
