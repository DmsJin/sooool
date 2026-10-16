import json
from pathlib import Path
import tempfile
import unittest

from research.api_client import ApiClient
from research.budget import BudgetError, BudgetLedger
from research.scheduler import parse_plan
from research.wire_schema import grounded_schema

ANSWER=json.dumps({'player':[10,20],'boss':[30,40],'aim_x':30,'plan':[{'move':3,'shoot':1,'focus':1,'bomb':0,'duration':12}]})


def sse(event):return b'data: '+json.dumps(event).encode()


class Stream:
    status_code=200
    def __init__(self,events):self.events=events
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_lines(self,**kwargs):
        for event in self.events:
            if callable(event):event()
            else:yield sse(event)


class Session:
    def __init__(self,events):self.events=events;self.calls=0
    def post(self,*args,**kwargs):self.calls+=1;return Stream(self.events)


class EarlyApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'ledger.json';self.ledger=BudgetLedger(self.path)
        self.png=b'\x89PNG\r\n\x1a\n'+b'\0'*8+(640).to_bytes(4,'big')+(480).to_bytes(4,'big')
    def tearDown(self):self.temp.cleanup()
    def terminal(self,kind='response.completed',usage=True,**extra):
        response={'model':'gpt-6.1-sol','service_tier':'ultrafast',**extra}
        if usage:response['usage']={'input_tokens':20,'output_tokens':53}
        return {'type':kind,'response':response}
    def client(self,events):
        session=Session(events);return ApiClient('offline-mock-key',self.path,session=session,output_schema=grounded_schema(1,48)),session
    def decide(self,client,callback):return client.decide('observe',[self.png],validate=parse_plan,on_legal_action=callback)

    def test_full_schema_action_delivers_once_before_terminal_with_inflight_budget(self):
        deliveries=[]
        def inspect_before_terminal():
            self.assertEqual(len(deliveries),1)
            self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'inflight')
        client,session=self.client([{'type':'response.output_text.delta','delta':ANSWER[:30]},
            lambda:self.assertEqual(deliveries,[]),{'type':'response.output_text.delta','delta':ANSWER[30:]},
            inspect_before_terminal,{'type':'response.output_text.delta','delta':'\n'},self.terminal()])
        result=self.decide(client,deliveries.append)
        self.assertEqual(len(deliveries),1);self.assertTrue(deliveries[0]['meta']['terminal_pending'])
        self.assertNotIn('usd',deliveries[0]['meta']);self.assertTrue(result['meta']['early_legal_delivered'])
        self.assertEqual(session.calls,1)
        self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'settled')

    def test_complete_json_outside_strict_schema_does_not_deliver(self):
        invalid=json.dumps({'plan':[{'move':3,'shoot':1,'focus':1,'bomb':0,'duration':12}]})
        deliveries=[];client,session=self.client([{'type':'response.output_text.delta','delta':invalid},self.terminal()])
        with self.assertRaises(Exception):self.decide(client,deliveries.append)
        self.assertEqual(deliveries,[]);self.assertTrue(self.ledger.snapshot()['blocked'])
        self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'settled')

    def test_incomplete_after_early_action_settles_then_blocks_new_admission(self):
        deliveries=[];client,session=self.client([{'type':'response.output_text.delta','delta':ANSWER},self.terminal('response.incomplete')])
        with self.assertRaises(RuntimeError):self.decide(client,deliveries.append)
        self.assertEqual(len(deliveries),1)
        self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'settled')
        with self.assertRaises(BudgetError):self.ledger.reserve('profile','.01')

    def test_missing_usage_after_early_action_keeps_reservation_unknown(self):
        deliveries=[];client,session=self.client([{'type':'response.output_text.delta','delta':ANSWER},self.terminal(usage=False)])
        with self.assertRaises(RuntimeError):self.decide(client,deliveries.append)
        self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'unknown')
        self.assertTrue(self.ledger.snapshot()['blocked'])

    def test_consumer_error_still_drains_and_settles(self):
        drained=[];client,session=self.client([{'type':'response.output_text.delta','delta':ANSWER},lambda:drained.append(True),self.terminal()])
        def fail(_):raise ValueError('consumer failure')
        with self.assertRaisesRegex(RuntimeError,'consumer failed'):self.decide(client,fail)
        self.assertEqual(drained,[True]);self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'settled')
        self.assertTrue(self.ledger.snapshot()['blocked'])

    def test_terminal_model_mismatch_remains_unknown_failclosed(self):
        client,session=self.client([{'type':'response.output_text.delta','delta':ANSWER},self.terminal(model='wrong-model')])
        with self.assertRaisesRegex(RuntimeError,'model/tier mismatch'):self.decide(client,lambda _:None)
        self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'unknown')

    def test_changed_terminal_canonical_text_blocks_after_settlement(self):
        client,session=self.client([{'type':'response.output_text.delta','delta':ANSWER},self.terminal(output=[{'content':[{'type':'output_text','text':ANSWER+'x'}]}])])
        with self.assertRaisesRegex(RuntimeError,'canonical text'):self.decide(client,lambda _:None)
        self.assertEqual(next(iter(self.ledger.snapshot()['requests'].values()))['status'],'settled')
        self.assertTrue(self.ledger.snapshot()['blocked'])

    def test_callback_without_strict_schema_rejected_before_reservation(self):
        client=ApiClient('offline-mock-key',self.path,session=Session([]))
        with self.assertRaises(ValueError):self.decide(client,lambda _:None)
        self.assertFalse(self.path.exists())


if __name__=='__main__':unittest.main()
