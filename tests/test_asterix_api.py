import json
from pathlib import Path
import sys
import tempfile
import subprocess
import unittest
from unittest.mock import patch

from runtime.cli import ROOT
sys.path.insert(0, str(ROOT/'environments/asterix'))
from runtime.asterix_api import AsterixApiClient, DiagnosticResponse, SCHEMA


class AsterixApiTransport(unittest.TestCase):
    def test_console_import_outside_repository(self):
        with tempfile.TemporaryDirectory() as d:
            result=subprocess.run([sys.executable,'-c','from runtime.asterix_api import AsterixApiClient'],cwd=d,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_failure_diagnostics_keep_codes_but_exclude_private_payloads(self):
        class Response:
            status_code=200
            headers={'x-request-id':'req-test','authorization':'secret-must-not-persist'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_lines(self,**kwargs):
                for event in [{'type':'response.reasoning_text.delta','delta':'private-thought'},
                              {'type':'error','code':'provider_failure','message':'private prompt contents'}]:
                    yield b'data: '+json.dumps(event).encode()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)
            with DiagnosticResponse(Response(),path) as response:list(response.iter_lines())
            text=(path/'transport.json').read_text();data=json.loads(text)
            self.assertEqual(data['provider_request_id'],'req-test')
            self.assertEqual(data['response_metadata'][0]['error_code'],'provider_failure')
            for secret in ['private-thought','private prompt contents','secret-must-not-persist']:
                self.assertNotIn(secret,text)

    def test_public_action_is_published_before_terminal_and_limit_stops_before_network(self):
        with tempfile.TemporaryDirectory() as d,patch('runtime.asterix_api.ApiClient') as factory:
            root=Path(d)
            api=factory.return_value
            api.ledger.snapshot.return_value={'requests':{},'blocked':None}
            client=AsterixApiClient(key='test-only',ledger=root/'ledger.json',budget=5,max_calls=1,output=root/'transport')
            def decide(text,images,validate,on_legal_action):
                answer='{"action":4,"reason":"Chase the food below."}'
                self.assertTrue(validate(answer))
                on_legal_action({'answer':answer,'meta':{'terminal_pending':True}})
                early=client.poll_action()
                self.assertEqual((early['chosen'],early['directory']),(4,'call-00000'))
                self.assertTrue(early['meta']['terminal_pending'])
                return {'answer':answer,'meta':{'usage':{},'usd':'0.01'}}
            api.decide.side_effect=decide
            answer,meta=client.act('task',[b'image'],root/'call-00000')
            self.assertEqual(json.loads(answer)['action'],4)
            self.assertEqual(factory.call_args.kwargs['output_schema'],SCHEMA)
            self.assertEqual((root/'call-00000/image-0.png').read_bytes(),b'image')
            self.assertTrue((root/'call-00000/response.json').exists())
            with self.assertRaises(RuntimeError):client.act('task',[b'image'],root/'call-00001')
            api.decide.assert_called_once()
            client.close()
            self.assertTrue((root/'transport/accounting.json').exists())
