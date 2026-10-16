import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from research.tracking_benchmark import score_trace, validated_comparisons, digest


def frame(**kw):
    return dict(player_x=100,boss_x=100,player_dx=0,held=[0,1,1,0],alive=True,
        shot_hits=0,bomb_orb_hits=0,hp_loss=0,hits=0,bombs_used=0,respawn=False,**kw)


class TrackingScoreTests(unittest.TestCase):
    def test_comparison_batch_empty_or_missing_case_fails_closed(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);manifest={'cases':[{'id':'left'},{'id':'right'}]}
            with self.assertRaisesRegex(ValueError,'No completed'):
                validated_comparisons(root,manifest,root)
            call=root/'call_001';call.mkdir();(call/'prompt.txt').write_text('game task')
            answer={'case_id':'left','candidate':'base','repeat':0,
                'prompt_sha256':digest(call/'prompt.txt'),'response':{'answer':json.dumps({'plan':[[0,1,1,0,1]]})}}
            (call/'comparison.json').write_text(json.dumps(answer))
            with self.assertRaisesRegex(ValueError,'Incomplete'):
                validated_comparisons(root,manifest,root)

    def test_bomb_damage_cannot_earn_tracking_reward(self):
        f=frame();f.update(bomb_orb_hits=8,hp_loss=240,bombs_used=1)
        frames=[frame() for _ in range(180)];frames[60]=f
        result=score_trace(frames)
        self.assertEqual(result['tracking_reward'],0)
        self.assertEqual(result['bomb_damage'],240)
        self.assertEqual(result['safety']['bombs_used'],1)

    def test_refill_does_not_cancel_gross_bomb_use(self):
        fs=[frame() for _ in range(180)]
        fs[61].update(bombs_used=1,net_bombs_used=1,lives_before=3,lives_after=3)
        fs[100].update(bombs_used=0,net_bombs_used=-1,bombs_gained=1,deaths=1,hits=1)
        fs[-1].update(lives_after=2)
        safety=score_trace(fs)['safety']
        self.assertEqual(safety['bombs_used'],1)
        self.assertEqual(safety['net_bombs_used'],0)
        self.assertEqual(safety['bombs_gained'],1)
        self.assertEqual(safety['deaths'],1)
        self.assertEqual(safety['lives_after'],2)

    def test_warmup_ignores_old_inflight_shots_fixed_denominator(self):
        fs=[frame() for _ in range(180)]
        fs[0]['shot_hits']=2;fs[60]['shot_hits']=2
        result=score_trace(fs)
        self.assertEqual(result['shot_damage_warmup'],10)
        self.assertEqual(result['shot_damage_after_warmup'],10)
        self.assertAlmostEqual(result['tracking_reward'],20/360)
        self.assertAlmostEqual(result['steady_tracking_reward'],10/240)
        self.assertEqual(score_trace(fs[:61])['tracking_reward'],result['tracking_reward'])

    def test_dead_and_not_shooting_break_miss_runs(self):
        fs=[frame() for _ in range(12)]
        fs[4]['alive']=False;fs[8]['held']=[0,0,1,0]
        result=score_trace(fs,warmup=0)
        self.assertEqual(result['longest_eligible_no_hit_ticks'],4)
        self.assertEqual(result['dead_ticks'],1)
        self.assertEqual(result['not_shooting_alive_ticks'],1)

    def test_first_chunk_movement_included_in_full_window_diagnostics(self):
        fs=[frame() for _ in range(180)]
        for f in fs[:48]:f.update(player_dx=-2,player_x=100,boss_x=130,held=[7,1,1,0])
        result=score_trace(fs,observed_boss_x=80)
        self.assertEqual(result['full_window_moving_ticks'],48)
        self.assertEqual(result['full_window_moving_away_from_current_boss_ticks'],48)
        self.assertEqual(result['full_window_stale_position_chase_ticks'],48)
        self.assertEqual(result['steady_moving_ticks'],0)
        self.assertEqual(result['steady_stale_position_chase_ticks'],0)
        self.assertEqual(result['moving_ticks'],0)
        self.assertEqual(result['tracking_reward'],0)
        fs[0]['respawn']=True
        after=score_trace(fs,observed_boss_x=80)
        self.assertEqual(after['full_window_moving_ticks'],47)
        self.assertEqual(after['full_window_stale_position_chase_ticks'],47)
        self.assertEqual(after['safety'],result['safety'])
        self.assertEqual(after['tracking_reward'],result['tracking_reward'])

    def test_stale_chase_is_diagnostic_and_respawn_is_not_move(self):
        f=frame();f.update(player_dx=-2,player_x=100,boss_x=130)
        result=score_trace([f],warmup=0,observed_boss_x=80)
        self.assertEqual(result['stale_position_chase_ticks'],1)
        self.assertEqual(result['moving_away_from_current_boss_ticks'],1)
        f['respawn']=True
        self.assertEqual(score_trace([f],warmup=0,observed_boss_x=80)['stale_position_chase_ticks'],0)

if __name__=='__main__':unittest.main()
