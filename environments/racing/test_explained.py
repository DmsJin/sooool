import pathlib,sys,json,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent));sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from explained_api import ExplainedAPI,parse_packet,OLD_FORMAT
from run import Budget,MODEL
from unittest.mock import Mock
class TestPacket(unittest.TestCase):
 def test_summary_and_action_publish_together_before_drain(self):
  with tempfile.TemporaryDirectory() as td:
   d=pathlib.Path(td);api=ExplainedAPI('LOCAL_TEST_ONLY',Budget(d/'mock_budget.json'));events=[];text='{"decision_summary":"Keep the outer lane through the bend.","action":[[3.5,-0.38,1.8]]}';identity={'model':MODEL,'service_tier':'ultrafast'}
   def lines():
    yield ('data: '+json.dumps({'type':'response.created','response':identity})).encode()
    yield ('data: '+json.dumps({'type':'response.output_text.delta','delta':text})).encode()
    self.assertEqual(events[0][0],[[3.5,-.38,1.8]]);self.assertEqual(events[0][1]['decision_summary'],'Keep the outer lane through the bend.')
    yield ('data: '+json.dumps({'type':'response.completed','response':{**identity,'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':text}]}],'usage':{'input_tokens':1000,'output_tokens':50}}})).encode()
   r=Mock();r.status_code=200;r.__enter__=Mock(return_value=r);r.__exit__=Mock(return_value=False);r.iter_lines=Mock(side_effect=lambda **kw:lines());api.http.post=Mock(return_value=r);answer,meta=api.act(OLD_FORMAT,[],d/'response',on_ready=lambda rows,meta:events.append((rows,meta)));self.assertEqual(json.loads(answer),[[3.5,-.38,1.8]]);self.assertEqual(json.loads((d/'response/result.json').read_text())['answer'],text);api.close()
 def test_order_and_bounds(self):
  for text in ['{"action":[[3,0,2]],"decision_summary":"Safe."}','{"decision_summary":"Safe.","action":[[4.1,0,2]]}','{"decision_summary":"Safe.","action":[[true,0,2]]}']:
   with self.assertRaises(ValueError):parse_packet(text)
if __name__=='__main__':unittest.main()
