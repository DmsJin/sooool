import json
from collections import deque
from concurrent.futures import Future
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.run_episode import remember_model_estimate, run


class VisualMemoryTests(unittest.TestCase):
    def test_only_finite_reported_coordinates_and_monotonic_observations(self):
        memory=deque(maxlen=2)
        remember_model_estimate(memory,{'answer':'{"boss":[10,20]}'},5)
        remember_model_estimate(memory,{'answer':'{"boss":[11,21]}'},5)
        remember_model_estimate(memory,{'answer':'{"boss":[999,999]}'},4)
        remember_model_estimate(memory,{'answer':'{"boss":[NaN,20]}'},6)
        self.assertEqual(list(memory),[{'frame':5,'boss':[11,21]}])

    def test_completed_native_future_cannot_leak_before_virtual_application(self):
        seen=[]
        class Env:
            def __init__(self,*args,**kwargs):self.frame=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def reset(self,*args,**kwargs):pass
            def clock(self):return {'frame':self.frame,'visual_frame':self.frame,'intro':0,'held':[0,1,1,0],'pending_plan':[]}
            def diagnostics(self):return {'clock':self.clock(),'state':{'status':'playing' if self.frame<7 else 'lost','tick':self.frame,'hits':0,'score':0,'boss':{'hp':1},'player':{'lives':1,'bombs':1}}}
            def capture(self):return {'frame':self.frame,'clock':self.clock(),'png':b'png','held':[0,1,1,0]}
            def advance(self,n):self.frame+=n
            def apply(self,plan):return self.clock()
        class Pool:
            def __init__(self,*args):self.seq=0
            def submit(self,prompt,images,directory):
                answer={'boss':[100+self.seq,200],'plan':[[0,1,1,0,1]]};self.seq+=1
                future=Future();future.set_result({'answer':json.dumps(answer),'plan':answer['plan'],'meta':{}})
                return future
            def close(self):pass
        def prompt(candidate,observation,*args):
            seen.append((observation['frame'],json.loads(json.dumps(observation['visual_memory']))))
            return 'visual task'
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);profile=root/'profile.json';profile.write_text('{"samples_s":[1]}')
            config={'profile':str(profile),'url':'unused','seed':1,'candidate':'unused','provider':'subscription','mode':'sim','workers':1,'capacity':2,'image_stride':1,'decision_stride':1,'visual_memory_points':8}
            with patch('research.run_episode.BrowserEnv',Env),patch('research.run_episode.DecisionPool',Pool),patch('research.run_episode.make_prompt',side_effect=prompt),patch('research.run_episode.sample_delay',return_value=5):
                run(config,root/'episode')
        self.assertEqual(seen[0],(0,[]))
        self.assertEqual(seen[1],(1,[]))
        self.assertEqual(seen[2],(5,[{'frame':0,'boss':[100,200]}]))
        self.assertEqual(seen[3],(6,[{'frame':0,'boss':[100,200]},{'frame':1,'boss':[101,200]}]))


if __name__=='__main__':unittest.main()
