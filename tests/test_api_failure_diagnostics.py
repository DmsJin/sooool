import json
from pathlib import Path
import tempfile
import unittest

from runtime.asterix_api import ApiClient, AsterixApiClient


class Response:
    status_code=200
    def __init__(self, events, content_type='text/event-stream'):
        self.events=events
        self.headers={'Content-Type':content_type,'x-request-id':'req-diagnostic'}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_lines(self,**kwargs):
        for event in self.events:yield b'data: '+json.dumps(event).encode()


class Session:
    calls=0
    def __init__(self,response):self.response=response
    def post(self,*args,**kwargs):
        self.calls+=1
        return self.response
    def close(self):pass


class FailureDiagnostics(unittest.TestCase):
    def check_failure(self, events, expected, *, content_type='text/event-stream', settled=False):
        png=b'\x89PNG\r\n\x1a\n'+b'\0'*8+(224).to_bytes(4,'big')+(224).to_bytes(4,'big')
        with tempfile.TemporaryDirectory() as d:
            session=Session(Response(events,content_type))
            client=ApiClient('test-only',Path(d)/'ledger.json',session=session)
            with self.assertRaisesRegex(RuntimeError,expected) as caught:client.decide('task',[png])
            diagnostic=getattr(caught.exception,'diagnostics',{})
            self.assertEqual(diagnostic['provider_request_id'],'req-diagnostic')
            self.assertNotIn('private input',str(caught.exception)+json.dumps(diagnostic))
            entry=next(iter(client.ledger.snapshot()['requests'].values()))
            self.assertEqual(entry['status'],'settled' if settled else 'unknown')
            self.assertEqual(session.calls,1)
            if not settled:self.assertTrue(client.ledger.snapshot()['blocked'])

    def test_error_event_is_not_reported_as_missing_usage(self):
        self.check_failure([{'type':'error','code':'rate_limit_exceeded','message':'private input'}], 'rate_limit_exceeded')

    def test_failed_terminal_without_usage_preserves_provider_code(self):
        self.check_failure([{'type':'response.failed','response':{'id':'resp-test','status':'failed','usage':None,
            'error':{'code':'server_error','message':'private input'}}}], 'server_error')

    def test_failed_terminal_with_usage_still_settles_billing(self):
        self.check_failure([{'type':'response.failed','response':{'id':'resp-test','status':'failed',
            'model':'gpt-6.1-sol','service_tier':'ultrafast','usage':{'input_tokens':20,'output_tokens':10},
            'error':{'code':'server_error','message':'private input'}}}], 'server_error',settled=True)

    def test_non_sse_success_status_has_distinct_protocol_error(self):
        self.check_failure([], 'Expected SSE',content_type='application/json')

    def test_cut_off_stream_is_distinct_from_terminal_without_usage(self):
        self.check_failure([{'type':'response.created','response':{'id':'resp-test'}}], 'missing_terminal_event')
        self.check_failure([{'type':'response.completed','response':{'id':'resp-test','status':'completed'}}], 'missing_terminal_usage')

    def test_asterix_failure_file_retains_shared_client_diagnostics(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            client=AsterixApiClient(key='test-only',ledger=root/'ledger.json',budget=10,max_calls=1,output=root/'transport')
            client.session.session=Session(Response([{'type':'error','code':'server_error','message':'private input'}]))
            png=b'\x89PNG\r\n\x1a\n'+b'\0'*8+(224).to_bytes(4,'big')+(224).to_bytes(4,'big')
            call=root/'call-00000'
            with self.assertRaisesRegex(RuntimeError,'server_error'):client.act('task',[png],call)
            failure=json.loads((call/'failure.json').read_text())
            self.assertEqual(failure['diagnostics']['provider_error_code'],'server_error')
            self.assertEqual(failure['diagnostics']['content_type'],'text/event-stream')
            self.assertEqual(failure['diagnostics']['event_counts'],{'error':1})
            self.assertIsNone(client.poll_action())
            client.close()
