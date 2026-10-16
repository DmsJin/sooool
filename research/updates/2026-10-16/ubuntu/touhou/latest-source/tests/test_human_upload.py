import base64
import json
from pathlib import Path
import tempfile
import unittest

from research.human_record import persist_event_batch, persist_frame_batch


class HumanUploadBatchTests(unittest.TestCase):
    def test_ordered_event_retry_does_not_duplicate_edges_or_actions(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            first={'batch_seq':0,'keys':[{'code':'KeyZ','down':True}],
                   'actions':[{'visual_frame':165,'action':[0,1,1,0]}]}
            second={'batch_seq':1,'keys':[{'code':'KeyZ','down':False}],'actions':[]}
            persist_event_batch(root,first);persist_event_batch(root,first)
            persist_event_batch(root,second);persist_event_batch(root,first)
            self.assertEqual(len((root/'key_edges.jsonl').read_text().splitlines()),2)
            self.assertEqual(len((root/'actions.jsonl').read_text().splitlines()),1)
            with self.assertRaises(AssertionError):persist_event_batch(root,first|{'keys':[]})
            with self.assertRaises(AssertionError):persist_event_batch(root,second|{'batch_seq':3})

    def test_frames_retry_deduplicates_and_keeps_real_recaptures(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'frames').mkdir()
            png='data:image/png;base64,'+base64.b64encode(b'\x89PNG\r\n\x1a\nTEST').decode()
            frame={'png':png,'frame':1,'held':[0,1,1,0],
                   'clock':{'visual_frame':166,'wall_ms':2800.0}}
            persist_frame_batch(root,[frame]);persist_frame_batch(root,[frame])
            later=frame|{'clock':{'visual_frame':166,'wall_ms':2801.0}}
            persist_frame_batch(root,[later])
            rows=[json.loads(s) for s in (root/'frames.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),2)
            self.assertTrue(all((root/row['png']).exists() for row in rows))
            self.assertEqual([row['clock']['wall_ms'] for row in rows],[2800.0,2801.0])


if __name__=='__main__':unittest.main()
