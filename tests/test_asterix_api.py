import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from runtime.cli import ROOT
sys.path.insert(0, str(ROOT/'environments/asterix'))
from runtime.asterix_api import AsterixApiClient, SCHEMA


class AsterixApiTransport(unittest.TestCase):
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
