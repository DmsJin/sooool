import json
from pathlib import Path
import random
import tempfile
import unittest
from research.control_delays import calibrate, sample_cohort_delay_frames


class ControlDelayTest(unittest.TestCase):
    def fixture(self, root):
        p=Path(root)
        (p/'summary.json').write_text(json.dumps({'complete':True}))
        (p/'config.json').write_text(json.dumps({'provider':'api','mode':'realtime','decision_fanout':4,'speed':1}))
        rows=[]
        for c in range(2):
            for i in range(4):
                rows.append({'seq':4*c+i,'cohort_id':c,'fanout_index':i,'visual_frame':c*60,
                             'decision_fanout':4,'capture_clock':{'wall_ms':1000*c},
                             'image_frames':[0] if c==0 else [0,30,60]})
        def write(name,data):
            (p/name).write_text(''.join(json.dumps(r)+'\n' for r in data))
        write('issued.jsonl',rows)
        write('decisions.jsonl',[dict(r,completed_wall_s=2+r['cohort_id']+[1,1.2,1.4,1.6][r['fanout_index']]) for r in rows[:4]] + rows[4:])
        write('actions.jsonl',[{'observed_frame':0,'applied_wall_s':3.1,'apply_clock':{'wall_ms':1100},'age_frames':66}])
        return p

    def test_joint_offset_terminal_and_applied_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(tmp)
            profile=calibrate([p])
            for a,b in zip(profile['joint_delay_vectors_s'][0],[1,1.2,1.4,1.6]):self.assertAlmostEqual(a,b)
            self.assertEqual(profile['provenance'][0]['excluded_terminal_cohorts'],[1])
            self.assertAlmostEqual(profile['control_age_p50_s'],1.1)
            self.assertEqual(profile['image_counts'],[1])
            self.assertEqual(sample_cohort_delay_frames(profile,random.Random(7)),[62,74,86,98])
            with self.assertRaises(ValueError):sample_cohort_delay_frames(profile,random.Random(7),image_count=3)

    def test_nonterminal_missing_candidate_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(tmp)
            rows=[json.loads(line) for line in (p/'decisions.jsonl').read_text().splitlines()]
            for row in rows[4:]:row['completed_wall_s']=4+row['fanout_index']/10
            del rows[0]['completed_wall_s']
            (p/'decisions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError):calibrate([p])

    def test_joint_sampling_preserves_correlation_and_speed(self):
        profile={'k':4,'joint_delay_vectors_s':[[1,2,3,4],[4,3,2,1]],'image_counts':[1,3],'apply_overhead_s':0}
        rng=random.Random(5)
        self.assertEqual(sample_cohort_delay_frames(profile,rng,.5,image_count=3),[120,90,60,30])
        for _ in range(20):self.assertIn(sample_cohort_delay_frames(profile,rng),[[60,120,180,240],[240,180,120,60]])

    def test_fail_closed_bad_metadata_and_vectors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=self.fixture(tmp)
            rows=[json.loads(line) for line in (p/'decisions.jsonl').read_text().splitlines()]
            rows[0]['completed_wall_s']=-1
            (p/'decisions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError):calibrate([p])
        for bad in [[1,float('nan'),2,3],[1,float('inf'),2,3],[1,-1,2,3],[1,2,3]]:
            with self.assertRaises(ValueError):sample_cohort_delay_frames({'k':4,'joint_delay_vectors_s':[bad],'image_counts':[1],'apply_overhead_s':0},random.Random(1))


if __name__=='__main__':unittest.main()
