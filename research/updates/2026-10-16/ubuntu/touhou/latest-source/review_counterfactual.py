"""Private paired evaluation of reviewed fixtures. Never calls a model or controls live play."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from .counterfactual_devset import advance, replay, load, rows, save
from .environment import BrowserEnv
from .human_counterfactual import replay_human
from .scheduler import parse_plan
from .state_compare import compare_engine_state
from .tracking_benchmark import ENGINE_SHA256, source, verify, score_trace, trace

SIMULATE = '''async({entries})=>{
 const {Game}=await import('/game/engine.mjs');const results=[];
 for(const entry of entries){
  const g=new Game(entry.seed),s=structuredClone(entry.before.state);
  for(const key of ['tick','player','boss','bullets','shots','bombOrbs','bombTimer','events','score','graze','status','hits'])g[key]=s[key];
  g.lastBomb=!!entry.before.clock.held[3];
  if(JSON.stringify(g.snapshot())!==JSON.stringify(s))throw Error('Private engine clone differs');
  const out=[];let i=0;
  while(i<180&&g.status==='playing'){
   const pre=g.snapshot(),p={...g.player};let offset=i,keys=[0,entry.plan.at(-1)[1],entry.plan.at(-1)[2],0];
   for(const action of entry.plan){if(offset<action[4]){keys=action.slice(0,4);break;}offset-=action[4];}
   g.step(keys);const q=g.player,b=g.boss,events=g.events,orbs=events.filter(e=>e.type==='orb_hit').length;
   const shotHits=(g.score-pre.score-25*(g.graze-pre.graze)-60*orbs)/10;
   if(!Number.isInteger(shotHits)||shotHits<0)throw Error('Invalid shot accounting');
   out.push({tick:g.tick,visual_frame:null,player_x:q.x,player_y:q.y,boss_x:b.x,boss_y:b.y,player_dx:q.x-p.x,held:keys,alive:p.dying===0,shot_hits:shotHits,bomb_orb_hits:orbs,hp_loss:pre.boss.hp-b.hp,hits:g.hits-pre.hits,bombs_used:events.filter(e=>e.type==='bomb').length,net_bombs_used:p.bombs-q.bombs,bombs_gained:Math.max(0,q.bombs-p.bombs),lives_before:p.lives,lives_after:q.lives,deaths:events.filter(e=>e.type==='crash').length,respawn:events.some(e=>e.type==='respawn')});i++;
  }
  results.push({key:entry.key,frames:out,final:g.snapshot()});
 }
 return results;
}'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(env, fixture, record, human, human_actions, api_sources, delay):
    origin=record['source'];at=origin['source_visual_frame']
    if 'source_episode' in origin:
        env.page.evaluate('research.setHuman(false)')
        original=api_sources[origin['source_episode']]
        issued=next(r for r in original['issued'] if r['seq']==origin['source_seq'])
        observed=replay(env,original,at,issued['capture_clock'].get('wall_ms'))
    else:
        observed=replay_human(env,load(human/'manifest.json')['seed'],human_actions,at)
        env.page.evaluate('research.setHuman(false)')
        held=load(fixture['input_path'])['observation']['held']
        env.apply([held+[1]])
    if observed['state']['tick']!=origin['source_logical_frame']:
        raise ValueError('Observed state clock mismatch')
    before=advance(env,at+math.ceil(delay*60))
    return {'seed':1,'observed':observed,'before':before,'pre_action_hits':before['state']['hits']-observed['state']['hits']}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--review-dataset',type=Path,required=True)
    p.add_argument('--human-source',type=Path,required=True)
    p.add_argument('--comparison',type=Path,required=True)
    p.add_argument('--instant-comparison',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expected-candidates',type=int,default=3)
    p.add_argument('--expected-repeats',type=int,default=2)
    p.add_argument('--url',default='http://127.0.0.1:8796/game/')
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    if digest(Path(__file__).parents[1]/'dist/engine.mjs')!=ENGINE_SHA256:raise ValueError('Engine changed')
    fixtures=load(args.dataset/'manifest.json')['cases'];byid={c['id']:c for c in fixtures}
    origins={c['id']:c for c in load(args.review_dataset/'manifest.json')['examples']}
    cache_path=args.output/'private-prefix-cache.json'
    answers=[];coverage=set()
    for directory,condition in [(args.comparison,'delayed'),(args.instant_comparison,'instant')]:
        for path in sorted(directory.glob('call_*/comparison.json')):
            a=load(path);case=byid[a['case_id']]
            if case['condition']!=condition:continue
            key=(a['case_id'],a['candidate'],a['repeat'])
            if key in coverage:raise ValueError('Duplicate response')
            coverage.add(key)
            if digest(path.parent/'prompt.txt')!=a['prompt_sha256']:raise ValueError('Prompt changed')
            if a['response']['meta']['image_sha256s']!=[i['sha256'] for i in case['images']]:raise ValueError('Image provenance differs')
            plan=parse_plan(a['response']['answer'])
            if len(plan)!=1 or plan[0].duration>48:raise ValueError('Frozen single-action contract exceeded')
            answers.append({**a,'plan_keys':[x.keys+[x.duration] for x in plan],'condition':condition})
    candidates={a['candidate'] for a in answers};expected={(c['id'],v,r) for c in fixtures for v in candidates for r in range(args.expected_repeats)}
    if coverage!=expected or len(candidates)!=args.expected_candidates:raise ValueError('Incomplete frozen 156-answer coverage')
    for c in fixtures:
        c['input_path']=args.dataset/c['input_file']
        if digest(c['input_path'])!=c['input_sha256']:raise ValueError('Input changed')
        for image in c['images']:
            if digest(args.dataset/image['file'])!=image['sha256']:raise ValueError('PNG changed')
    with BrowserEnv(args.url) as env:
        env.page.evaluate("()=>{for(const k of ['drawImage','fillRect','clearRect','stroke','fill','fillText','strokeText'])CanvasRenderingContext2D.prototype[k]=()=>{};}")
        human_actions=rows(args.human_source/'actions.jsonl');human_expected=load(args.human_source/'final_state.json')
        human_final=replay_human(env,1,human_actions,human_expected['clock']['visual_frame']);hv=compare_engine_state(human_final['state'],human_expected['state']);assert hv['bounded_float']
        api_sources={};validations={'human':hv}
        for record in origins.values():
            episode=record['source'].get('source_episode')
            if episode and episode not in api_sources:
                original=source(Path(episode));original['issued']=rows(Path(episode)/'issued.jsonl');api_sources[episode]=original;validations[episode]=verify(env,original)
        if cache_path.exists():
            cached=load(cache_path)
            if cached.get('fixture_manifest_sha256')!=digest(args.dataset/'manifest.json'):raise ValueError('Cached fixtures changed')
            cache=cached['entries']
        else:
            cache={}
            for c in fixtures:
                delays=[0] if c['condition']=='instant' else [2.2042,2.57086]
                for delay in delays:
                    key=c['id']+'@'+str(delay);cache[key]=prepare(env,c,origins[c['source_case']],args.human_source,human_actions,api_sources,delay)
            save(cache_path,{'fixture_manifest_sha256':digest(args.dataset/'manifest.json'),'source_verification':validations,'entries':cache})
        entries=[];metadata={}
        for a in answers:
            for delay in ([0] if a['condition']=='instant' else [2.2042,2.57086]):
                key='|'.join(map(str,[a['case_id'],a['candidate'],a['repeat'],delay]));entry=cache[a['case_id']+'@'+str(delay)];entries.append({'key':key,**entry,'plan':a['plan_keys']});metadata[key]={k:a[k] for k in ['case_id','candidate','repeat','condition','prompt_sha256']};metadata[key].update(delay_s=delay,pre_action_hits=entry['pre_action_hits'],before_lives=entry['before']['state']['player']['lives'],source_case=byid[a['case_id']]['source_case'])
        results=env.page.evaluate(SIMULATE,{'entries':entries})
        # Independently compare four clones against public original research playback.
        validation=[]
        for entry in [entries[i] for i in [0,len(entries)//3,2*len(entries)//3,len(entries)-1]]:
            meta=metadata[entry['key']];c=byid[meta['case_id']];prepare(env,c,origins[c['source_case']],args.human_source,human_actions,api_sources,meta['delay_s']);env.apply(entry['plan']);run=trace(env,ticks=180);private=next(r for r in results if r['key']==entry['key']);checked=compare_engine_state(run['final']['state'],private['final']);assert checked['bounded_float'];validation.append({'key':entry['key'],**checked})
    scored=[]
    for result in results:
        scored.append({**metadata[result['key']],'status_after':result['final']['status'],'metrics':score_trace(result['frames'],warmup=0),'frames':result['frames']})
    save(args.output/'private-results.json',{'complete':True,'model_answers':len(answers),'rollouts':scored,'engine_sha256':ENGINE_SHA256,'clone_public_replay_validation':validation,'boundary':'Private scoring only, no live action selection and no modified game reward. Historical pre-action losses separate. Fixed180 logical post-application ticks, original early game termination allowed and reported.'})
    print(json.dumps({'answers':len(answers),'rollouts':len(scored),'validated_clones':len(validation)}))


if __name__=='__main__':main()
