"""Freeze a matching profile and a predeclared subscription round."""
import argparse,json,pathlib,statistics
from .profile_api import percentile


def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=pathlib.Path,required=True);p.add_argument('--raw',type=pathlib.Path,required=True);p.add_argument('--round-name',default='round1');p.add_argument('--candidates',nargs='+',default=['baseline','predict','damage','conservative']);a=p.parse_args()
 rows=[json.loads(x) for x in a.raw.read_text().splitlines()];rows=[x for x in rows if x['group']=='native3_changing' and x['meta']['valid']]
 if len(rows)<15:raise ValueError('At least15 changing three-image samples required')
 samples=[x['meta']['total_s'] for x in rows];profile={'condition':'native640x480_detail_high_three_images_baseline_low_ultrafast','n':len(samples),'samples_s':samples,'p50_s':statistics.median(samples),'p95_s':percentile(samples,.95),'mean_usd':statistics.mean(float(x['meta']['usd']) for x in rows),'raw':str(a.raw),'limitation':'unloaded serial calibration; concurrency pressure is not empirically calibrated'}
 profilepath=a.root/'profile-game-v1.json';profilepath.write_text(json.dumps(profile,indent=2))
 base={'provider':'subscription','mode':'sim','url':'http://127.0.0.1:18791','suite':'/home/ubuntu/lzj/coding-agent-suite','profile':str(profilepath),'speed':1,'workers':3,'capacity':8,'history_frames':3,'image_stride':15,'decision_stride':30,'chunk_size':1,'max_duration':48,'max_wall_s':14400,'engine_sha256':'348e81340d4a09f8b488193daf0b4e395afa2755d34f249585ff5e1ffe787aa4','profile_note':'Prompt variants currently share baseline-profile delay; finalists will be serially recalibrated'}
 jobs=[{'name':f'{candidate}-seed{seed}','config':{'candidate':candidate,'seed':seed,'delay_seed':113+seed}} for candidate in a.candidates for seed in [2,5,6]]
 spec={'base':base,'jobs':jobs,'dev_seeds':[2,5,6],'unseen_api_seeds':[7,8,9],'max_actual_workers':24,'promotion':'Complete3seeds, rank won_count then bossHP, independent frozen repeat required','round_name':a.round_name}
 (a.root/(a.round_name+'.json')).write_text(json.dumps(spec,indent=2));print(json.dumps(profile));print(a.root/(a.round_name+'.json'))

if __name__=='__main__':main()
