from collections import deque
from concurrent.futures import Future
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.observation_history import ObservationHistory
from research.run_episode import run
from research.policies import make_prompt


class ObservationHistoryTests(unittest.TestCase):
    def test_default_is_the_original_deque_including_duplicate_clocks(self):
        history=ObservationHistory({'history_frames':3,'image_stride':30,'decision_stride':6})
        original=deque(maxlen=3)
        for index,frame in enumerate([0,0,6,12,12,30,60,90]):
            png=f'capture{index}@{frame}'.encode()
            original.append((frame,png));history.append(frame,png)
            self.assertEqual(history.select(),list(original))
        # Legacy anchors cadence to the old loop clock even if capture is newer.
        self.assertEqual(history.next_capture_after(90,{'clock':{'visual_frame':95}}),120)
        self.assertEqual(ObservationHistory({}).capture_stride,15)

    def test_fresh_latest_preserves_spaced_past_pngs(self):
        history=ObservationHistory({'capture_stride':6,'history_spacing_frames':30,'history_frames':3})
        for frame in range(0,73,6):
            history.append(frame,f'PNG:{frame}'.encode())
        self.assertEqual(history.select(),[(12,b'PNG:12'),(42,b'PNG:42'),(72,b'PNG:72')])
        self.assertEqual(history.next_capture_after(72,{'clock':{'visual_frame':75}}),81)

    def test_startup_never_invents_an_older_frame_or_duplicates_one(self):
        history=ObservationHistory({'capture_stride':6,'history_spacing_frames':30})
        self.assertEqual(history.select(),[])
        for frame in (0,6,12,18,24):
            history.append(frame,str(frame).encode())
            self.assertEqual(history.select(),[(frame,str(frame).encode())])
        history.append(30,b'30')
        self.assertEqual(history.select(),[(0,b'0'),(30,b'30')])
        for frame in range(36,61,6):history.append(frame,str(frame).encode())
        self.assertEqual(history.select(),[(0,b'0'),(30,b'30'),(60,b'60')])

    def test_pause_replaces_same_logical_clock_with_latest_picture(self):
        history=ObservationHistory({'capture_stride':6,'history_spacing_frames':30})
        for visual in range(0,181,6):history.append(0,f'intro:{visual}'.encode())
        self.assertEqual(history.select(),[(0,b'intro:180')])
        self.assertEqual(len(history._samples),1)
        history.append(30,b'physics30');history.append(60,b'declaration-start')
        history.append(60,b'declaration-latest')
        self.assertEqual(history.select(),[(0,b'intro:180'),(30,b'physics30'),(60,b'declaration-latest')])

    def test_capture_only_override_deduplicates_without_forcing_spacing(self):
        history=ObservationHistory({'capture_stride':6})
        for frame,png in [(0,b'old0'),(0,b'new0'),(6,b'6'),(12,b'12')]:history.append(frame,png)
        self.assertEqual(history.select(),[(0,b'new0'),(6,b'6'),(12,b'12')])

    def test_irregular_samples_stay_past_and_chronological(self):
        history=ObservationHistory({'history_spacing_frames':30})
        samples=[0,7,13,29,31,38,61,67]
        for frame in samples:history.append(frame,str(frame).encode())
        self.assertEqual(history.select(),[(7,b'7'),(31,b'31'),(67,b'67')])
        self.assertTrue(all(frame<=67 and png==str(frame).encode()for frame,png in history.select()))
        # Long capture gaps must not repeat the only historical sample twice.
        gap=ObservationHistory({'history_spacing_frames':30})
        gap.append(0,b'0');gap.append(200,b'200')
        self.assertEqual(gap.select(),[(0,b'0'),(200,b'200')])

    def test_storage_bounded_by_required_span_and_single_image_supported(self):
        history=ObservationHistory({'capture_stride':1,'history_spacing_frames':30})
        for frame in range(10000):history.append(frame,b'PNG')
        self.assertLessEqual(len(history._samples),62)
        self.assertEqual([frame for frame,_ in history.select()],[9939,9969,9999])
        one=ObservationHistory({'capture_stride':6,'history_spacing_frames':30,'history_frames':1})
        for frame in range(100):one.append(frame,str(frame).encode())
        self.assertEqual(one.select(),[(99,b'99')]);self.assertEqual(len(one._samples),1)

    def test_bad_options_and_backwards_clock_fail_closed(self):
        for key in ('capture_stride','history_spacing_frames'):
            for value in (0,-1,None,True,1.5,'6'):
                with self.assertRaisesRegex(ValueError,key):ObservationHistory({key:value})
        for value in (0,4,True,1.5):
            with self.assertRaisesRegex(ValueError,'history_frames'):ObservationHistory({'history_frames':value})
        history=ObservationHistory({'capture_stride':6});history.append(12,b'current')
        with self.assertRaisesRegex(ValueError,'backwards'):history.append(6,b'stale')
        self.assertEqual(history.select(),[(12,b'current')])

    def test_options_do_not_add_or_change_task_instructions(self):
        obs={'image_frames':[12,42,72],'held':[0,1,1,0]}
        config={'structured':True,'wait_for_move':True,'pixel_controls':True}
        before=make_prompt('tracking_dodge_safe_intercept_v2',obs,config,{})
        after=make_prompt('tracking_dodge_safe_intercept_v2',obs,{**config,'capture_stride':6,'history_spacing_frames':30},{})
        self.assertEqual(before.encode(),after.encode())


class CaptureCadenceIntegrationTests(unittest.TestCase):
    def simulate(self, root, name, **overrides):
        class Env:
            def __init__(self,*args,**kwargs):self.frame=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def reset(self,*args,**kwargs):pass
            def clock(self):return {'frame':self.frame,'visual_frame':self.frame,'intro':0,'held':[0,1,1,0],'pending_plan':[],'status':'playing'}
            def diagnostics(self):
                return {'clock':self.clock(),'state':{'status':'playing' if self.frame<84 else 'lost',
                    'tick':self.frame,'hits':0,'score':0,'boss':{'hp':1},'player':{'lives':1,'bombs':1}}}
            def capture(self):return {'frame':self.frame,'clock':self.clock(),'png':f'PNG:{self.frame}'.encode(),'held':[0,1,1,0]}
            def advance(self,n):self.frame+=n
            def apply(self,plan):return self.clock()
        class Pool:
            def __init__(self,*args):pass
            def submit(self,prompt,images,directory):
                future=Future();future.set_result({'answer':'[[0,1,1,0,1]]','plan':[[0,1,1,0,1]],'meta':{}})
                return future
            def close(self):pass
        profile=root/'profile.json';profile.write_text('{"samples_s":[0.01]}')
        config={'profile':str(profile),'url':'unused','seed':1,'candidate':'tracking_dodge_safe_intercept_v2',
                'provider':'subscription','mode':'sim','decision_stride':6,'image_stride':30,
                'history_frames':3,'structured':True,**overrides}
        output=root/name
        with patch('research.run_episode.BrowserEnv',Env),patch('research.run_episode.DecisionPool',Pool),contextlib.redirect_stdout(io.StringIO()):
            run(config,output)
        return output,[json.loads(line)for line in (output/'issued.jsonl').read_text().splitlines()]

    def test_six_frame_latest_not_blocked_by_legacy_thirty_frame_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);out,rows=self.simulate(root,'fresh',capture_stride=6,history_spacing_frames=30)
            self.assertEqual([row['visual_frame']for row in rows],list(range(0,84,6)))
            row=next(row for row in rows if row['logical_frame']==72)
            self.assertEqual(row['image_frames'],[12,42,72])
            for row in rows:
                self.assertEqual(row['image_frames'][-1],row['logical_frame'])
                self.assertEqual(row['image_frames'],sorted(set(row['image_frames'])))
                for index,frame in enumerate(row['image_frames']):
                    png=(out/f'decision_{row["seq"]:05d}'/f'image_{index}.png').read_bytes()
                    self.assertEqual(png,f'PNG:{frame}'.encode())
                    self.assertEqual(hashlib.sha256(png).hexdigest(),row['image_sha256'][index])

    def test_omitted_options_keep_legacy_cadence_and_equivalent_prompt_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);_,old=self.simulate(root,'legacy')
            _,equivalent=self.simulate(root,'equivalent',capture_stride=30,history_spacing_frames=30)
            self.assertEqual([row['visual_frame']for row in old],[0,30,60])
            self.assertEqual([row['image_frames']for row in old],[[0],[0,30],[0,30,60]])
            for before,after in zip(old,equivalent):
                for key in ('visual_frame','logical_frame','image_frames','image_sha256','prompt_sha256','held','delay_frames'):
                    self.assertEqual(before[key],after[key])

    def test_invalid_opt_in_fails_before_output_client_or_browser(self):
        with tempfile.TemporaryDirectory() as temp,patch('research.run_episode.DecisionPool')as pool,patch('research.run_episode.BrowserEnv')as browser:
            output=Path(temp)/'episode'
            with self.assertRaisesRegex(ValueError,'capture_stride'):run({'capture_stride':0},output)
            self.assertFalse(output.exists());pool.assert_not_called();browser.assert_not_called()


if __name__=='__main__':unittest.main()
