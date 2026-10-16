import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from experiments.rhythm.model_training import run_episode


class FakeProvider:
    async def start(self): return self
    async def close(self): pass
    async def act(self, text, images):
        await asyncio.sleep(.001)
        version=json.loads(text.rsplit('\n',1)[1])['request_version']
        return json.dumps({'version':version,'cancel_ids':[], 'taps':[{'id':'literal','key':'d','at_ms':12345.6789,'expires_ms':12400.1234}]}), {'wall_seconds':.001}


class FakeEnv:
    applied=[]
    def __init__(self,*args,**kwargs):self.t=0;self.offset=kwargs['clock_offset_ms']
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def start(self):pass
    async def advance(self,seconds):self.t=seconds
    async def capture(self):return {'png':b'fixture','capture_start_ms':self.offset+self.t*1000,'capture_end_ms':self.offset+self.t*1000}
    async def snapshot(self):return {'clock_ms':self.offset+self.t*1000,'version':-1,'pending':[],'rawacks':[{'id':str(i),'status':'fixture'} for i in range(40)]}
    async def apply(self,plan):self.applied.append((self.t,plan));return {'transaction_status':'accepted'}
    async def trusted_evaluator(self):return {'state':'result' if self.t>=1 else 'playing','judged':52,'total_notes':52,'counts':{'perfect':52,'great':0,'ok':0,'miss':0}}


class TrainingCausalityTests(unittest.IsolatedAsyncioTestCase):
    async def test_virtual_delivery_preserves_literal_times_and_raw_ack_tail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);profile=root/'profile.json'
            profile.write_text(json.dumps({'rows':[{'status':'completed','metadata':{'latency_s':.5}}]}))
            args=SimpleNamespace(actors=1,cadence=.12,max_requests=1,frames=1,duration=1.001,candidate='fixture',profile=str(profile),seed=2,memory=None,run_root=str(root/'runs'),chart=None,clock_offset_ms=10000,url='fixture',browser_executable=None)
            FakeEnv.applied=[]
            result=await run_episode(args,provider_factory=FakeProvider,env_factory=FakeEnv)
            self.assertEqual(len(FakeEnv.applied),1)
            time,plan=FakeEnv.applied[0];self.assertEqual(time,.5)
            self.assertEqual(plan['taps'][0]['at_ms'],12345.6789)
            self.assertEqual(plan['taps'][0]['expires_ms'],12400.1234)
            folder=Path(result['output']);request=json.loads((folder/'requests.jsonl').read_text().splitlines()[0]);context=json.loads(request['prompt'].rsplit('\n',1)[1])
            self.assertEqual(len(context['executed_acks']),24)
            self.assertEqual(context['executed_acks'][0]['id'],'16')
            self.assertEqual(result['paid_api_calls'],0)
            self.assertEqual(folder.stat().st_mode&0o777,0o700)


if __name__=='__main__':unittest.main()
