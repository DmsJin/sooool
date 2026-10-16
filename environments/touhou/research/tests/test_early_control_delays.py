import json
from pathlib import Path
import random
import tempfile
import unittest
from concurrent.futures import Future
from research.early_control_delays import calibrate_early
from research.control_delays import sample_cohort_ready_terminal_frames
from research.scheduler import VirtualScheduler


class EarlyControlDelaysTest(unittest.TestCase):
    def fixture(self,root):
        p=Path(root)
        (p/'config.json').write_text(json.dumps(dict(mode='realtime',provider='api',speed=1,early_action_delivery=True,decision_fanout=2)))
        (p/'summary.json').write_text(json.dumps(dict(complete=True,terminal_accounting_complete=True)))
        issued=[];decisions=[];actions=[]
        for c in range(2):
            for i in range(2):
                seq=c*2+i
                row=dict(seq=seq,cohort_id=c,fanout_index=i,visual_frame=c*60,decision_fanout=2,capture_clock={'wall_ms':c*1000},image_frames=[0] if c==0 else [0,30,60])
                issued.append(row)
                early={'answer':'[0,1,1,0,1]','meta':{'early_legal':True,'stage_timing':{'early_legal_ready_wall_s':10+c+1+i*.2}}}
                directory=p/f'decision_{seq:05d}';directory.mkdir();(directory/'early_result.json').write_text(json.dumps(early))
                complete={**row,'answer':early['answer'],'meta':{'early_legal_delivered':True,'valid':True,'early_callback_s':.1,'stage_timing':{'result_durable_wall_s':10+c+1.3+i*.2}}}
                if c==0:complete['completed_wall_s']=11.5+i*.2
                decisions.append(complete)
            actions.append(dict(seq=2*c,observed_frame=c*60,applied_wall_s=11.2+c,apply_clock={'wall_ms':1200+c*1000},capture_to_apply_s=1.15,capture_start_to_apply_s=1.25,age_frames=72))
        for name,rows in [('issued.jsonl',issued),('decisions.jsonl',decisions),('actions.jsonl',actions)]:
            (p/name).write_text(''.join(json.dumps(r)+'\n' for r in rows))
        return p

    def test_callback_bound_and_explicit_terminal_tail(self):
        with tempfile.TemporaryDirectory() as root:
            p=self.fixture(root)
            with self.assertRaisesRegex(ValueError,'censored'):calibrate_early([p],k=2)
            profile=calibrate_early([p],k=2,apply_overhead_s=0,terminal_tail_policy='durable_plus_median_poll_lag')
            self.assertEqual(profile['image_counts'],[1,3])
            for row in profile['joint_delay_vectors_s']:
                self.assertAlmostEqual(row[0],1.1);self.assertAlmostEqual(row[1],1.3)
            for row in profile['joint_terminal_delay_vectors_s']:
                self.assertAlmostEqual(row[0],1.5);self.assertAlmostEqual(row[1],1.7)
            self.assertAlmostEqual(profile['control_age_p50_s'],1.2)
            self.assertEqual(profile['provenance'][0]['modeled_terminal_tail_cohorts'],[1])
            self.assertEqual(len(profile['provenance'][0]['early_file_sha256']),4)
            excluded=calibrate_early([p],k=2,terminal_tail_policy='exclude')
            self.assertEqual(excluded['image_counts'],[1])
            with self.assertRaisesRegex(ValueError,'stratum'):
                sample_cohort_ready_terminal_frames(profile,random.Random(1),image_count=2)

    def test_inconsistent_or_unverified_logs_fail_closed(self):
        for damage in ('accounting','answer','negative_callback','nonterminal_censor'):
            with self.subTest(damage=damage),tempfile.TemporaryDirectory() as root:
                p=self.fixture(root)
                if damage=='accounting':(p/'summary.json').write_text(json.dumps({'complete':True,'terminal_accounting_complete':False}))
                else:
                    rows=[json.loads(x) for x in (p/'decisions.jsonl').read_text().splitlines()]
                    if damage=='answer':rows[0]['answer']='[3,1,1,0,1]'
                    if damage=='negative_callback':rows[0]['meta']['early_callback_s']=-.1
                    if damage=='nonterminal_censor':del rows[0]['completed_wall_s']
                    (p/'decisions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
                with self.assertRaises(ValueError):calibrate_early([p],k=2,terminal_tail_policy='durable_plus_median_poll_lag')

    def test_pair_sampling_preserves_same_row_and_checks_terminal(self):
        p={'k':2,'joint_delay_vectors_s':[[1,2],[3,4]],'joint_terminal_delay_vectors_s':[[2,3],[4,5]],'image_counts':[1,3],'apply_overhead_s':.1}
        self.assertEqual(sample_cohort_ready_terminal_frames(p,random.Random(4),image_count=3),([186,246],[240,300]))
        p['joint_terminal_delay_vectors_s'][0][0]=.9
        with self.assertRaises(ValueError):sample_cohort_ready_terminal_frames(p,random.Random(1),image_count=3)

    def test_ready_action_holds_slot_until_terminal_without_duplicate(self):
        scheduler=VirtualScheduler(capacity=1,first_valid_per_observation=True)
        future=Future();future.set_result([3,1,1,0,2])
        self.assertEqual(scheduler.submit(0,future,2,terminal_delay_frames=8),0)
        self.assertEqual(scheduler.advance(2)[0]['disposition'],'applied')
        self.assertEqual(scheduler.inflight,1)
        self.assertFalse(scheduler.has_pending_observation(0))
        self.assertIsNone(scheduler.submit(2,future,1))
        self.assertEqual(scheduler.advance(7),[]);self.assertEqual(scheduler.inflight,1)
        self.assertEqual(scheduler.advance(8),[]);self.assertEqual(scheduler.inflight,0)
        self.assertEqual(scheduler.submit(8,future,2),1)
        self.assertEqual(scheduler.advance(10)[0]['disposition'],'applied')
        self.assertEqual(scheduler.inflight,0)

    def test_invalid_and_stale_actions_also_hold_slots(self):
        scheduler=VirtualScheduler(capacity=3,first_valid_per_observation=True)
        for answer in ([3,1,1,0,2],[7,1,1,0,2],['bad']):
            f=Future();f.set_result(answer);scheduler.submit(0,f,2,terminal_delay_frames=9)
        self.assertEqual([r['disposition'] for r in scheduler.advance(2)],['applied','stale','invalid'])
        self.assertEqual(scheduler.inflight,3)
        scheduler.advance(9);self.assertEqual(scheduler.inflight,0)
        with self.assertRaises(ValueError):scheduler.submit(9,Future(),5,terminal_delay_frames=4)

if __name__=='__main__':unittest.main()
