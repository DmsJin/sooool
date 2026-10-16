"""Native fixed-action calibration of legal serving margin; no GPT score claim."""
import argparse,json,os,sys
from pathlib import Path
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from core.episode import load_plugin,Episode
from core.local import _header
from core.sport import MatchConfig,parse_action,UNIT_OVER,FINISHED

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ys',default='0.4,0.45,0.5,0.55,0.6');p.add_argument('--seeds',default='2,5,6');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    plugin=str(ROOT/'sports/tabletennis/plugin.py');sport=load_plugin(plugin)
    from builtin_players import SERVES,serve_plan
    results=[]
    for y in map(float,a.ys.split(',')):
        recipe={**SERVES['short_centre_top'],'b2':(0.0,y)}
        plan=serve_plan('short_centre_top',recipe=recipe)
        if plan is None:results.append({'y':y,'status':'no analytic plan'});continue
        toss,stroke=plan
        action={key:stroke[key].round(5).tolist() for key in ('pos','normal','vel','base')}
        action.update(type='act',t=round(.2+stroke['t_from_projection'],4))
        for seed in map(int,a.seeds.split(',')):
            cfg=MatchConfig(sport='tabletennis',format='match',seats=('A',),seed=seed,level=1,slowdown=10)
            m=sport.build(cfg);layer=sport.action_layer('high')
            out=a.output/f'y{y}-seed{seed}';out.mkdir();ep=Episode(out/'episode.jsonl');_header(ep,sport,cfg)
            def effect(body):
                cmd=parse_action(layer,'A',body,m,{});low,info=layer.lower('A',cmd,None,m)
                ep.write('cmd',k=m.k,seat='A',cmd=low);m.apply('A',low);return info
            effect({'type':'move','base':stroke['base'].tolist()})
            while m.k<140:m.step()
            q_at_serve=m.observe('A')['q'];info=effect(action)
            while m.k<150:m.step()
            effect({'type':'toss',**toss})
            while m.k<900 and m.phase().state not in (UNIT_OVER,FINISHED):m.step()
            ep.write('end',k=m.k,reason='fixed_serve_calibration')
            row={'y':y,'seed':seed,'scores':m.scores(),'points':m.observe('A')['points'],'k':m.k,
                 'q_at_serve':q_at_serve,'action':action,'toss':toss,'stroke':info.get('stroke'),
                 'scope':'fixed native action calibration, no GPT calls','digest':m.state_digest()}
            (out/'summary.json').write_text(json.dumps(row,indent=2));results.append(row)
            (a.output/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps({k:row[k] for k in ('y','seed','scores','points','stroke')}),flush=True)

if __name__=='__main__':main()
