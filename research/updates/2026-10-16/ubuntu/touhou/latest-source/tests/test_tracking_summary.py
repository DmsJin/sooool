import copy
import unittest
from research.tracking_benchmark import DELAYS,ENGINE_SHA256,HORIZON,WARMUP
from research.tracking_summary import summarize


def report():
    rows=[]
    for candidate,damage in [('base',100),('tracking',150),('unsafe',200)]:
        for case in ['left','turn']:
            for delay in DELAYS:
                rows.append(dict(candidate=candidate,case_id=case,repeat=0,delay_s=delay,
                    metrics=dict(shot_damage=damage,shot_hits=damage//5,shot_damage_after_warmup=damage-20,
                        full_window_longest_eligible_no_hit_ticks=40,not_shooting_alive_ticks=0,logical_ticks=180,
                        safety=dict(hits=0,deaths=0,bombs_used=int(candidate=='unsafe')))))
    return dict(kind='private_tracking_benchmark_v1',complete=True,engine_sha256=ENGINE_SHA256,
        horizon_logical_ticks=HORIZON,warmup_logical_ticks=WARMUP,
        source_verification={'actual':{'bounded_float':True}},rollouts=rows,
        comparison_coverage=dict(cases=2,candidates=['base','tracking','unsafe'],answers=6,candidate_repeat_pairs=3))


class TrackingSummaryTests(unittest.TestCase):
    def test_bomb_damage_candidate_rejected_despite_higher_shot_score(self):
        result=summarize(report(),'base',12)
        self.assertEqual(result['selected_candidate'],'tracking')
        self.assertEqual(result['candidates']['unsafe']['safety_gate_failures'],['bombs_used'])
        self.assertEqual(result['candidates']['tracking']['paired_shot_damage_delta_mean'],50)

    def test_all_four_resource_gates_are_independent(self):
        for field in ['hits','deaths','bombs_used','not_shooting_alive_ticks']:
            with self.subTest(field=field):
                data=report()
                row=next(r for r in data['rollouts'] if r['candidate']=='tracking')
                target=row['metrics'] if field=='not_shooting_alive_ticks' else row['metrics']['safety']
                target[field]=1
                result=summarize(data,'base',12)
                self.assertEqual(result['selected_candidate'],'base')
                self.assertIn(field,result['candidates']['tracking']['safety_gate_failures'])

    def test_missing_or_duplicate_pair_fails_closed(self):
        data=report();data['rollouts'].pop()
        with self.assertRaisesRegex(ValueError,'row count'):summarize(data,'base',12)
        data=report();data['rollouts'][-1]=copy.deepcopy(data['rollouts'][-2])
        with self.assertRaisesRegex(ValueError,'Duplicate'):summarize(data,'base',12)
        data=report();data['rollouts'][-1]['case_id']='unknown'
        with self.assertRaisesRegex(ValueError,'coverage'):summarize(data,'base',12)

    def test_incomplete_report_and_changed_delay_rejected(self):
        data=report();data['complete']=False
        with self.assertRaises(ValueError):summarize(data,'base',12)
        data=report();data['rollouts'][0]['delay_s']=2.2
        with self.assertRaisesRegex(ValueError,'Delay'):summarize(data,'base',12)

    def test_exact_tie_retains_baseline(self):
        data=report()
        for row in data['rollouts']:
            if row['candidate']=='tracking':
                row['metrics'].update(shot_damage=100,shot_hits=20,shot_damage_after_warmup=80)
        self.assertEqual(summarize(data,'base',12)['selected_candidate'],'base')

if __name__=='__main__':unittest.main()
