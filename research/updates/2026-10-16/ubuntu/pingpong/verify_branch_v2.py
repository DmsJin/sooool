"""Qualified exact native replay for partial forks; never full acceptance evidence."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
from partial_evidence import resolve


def run(a):
    sys.path.insert(0,str(a.native_root));os.environ.setdefault('MUJOCO_GL','egl')
    from core.episode import load_plugin,header_cfg
    from core.local import Views
    from core import spec as spec_mod
    expected=json.loads((a.source/'summary.json').read_text())
    if not expected.get('branched') or expected.get('failure'):raise ValueError('Require valid partial development fork')
    rows=[json.loads(x) for x in (a.source/'episode.jsonl').read_text().splitlines()]
    cutoff=next(i for i,r in enumerate(rows) if r['ev']=='fork_start');post=rows[cutoff+1:]
    issued=[r for r in post if r['ev']=='model_issued']
    if len(issued)!=expected['calls']:raise ValueError('Missing issued decision records')
    evidence={r['seq']:resolve(a.source,r,post) for r in issued}
    plugin=str(a.native_root/'sports/tabletennis/plugin.py');sport=load_plugin(plugin)
    match=sport.build(header_cfg(rows[0]));cfg=header_cfg(rows[0])
    views=Views(sport,cfg,match,spec_mod.load(plugin),True,plugin)
    timeline={}
    for row in rows:
        if row['ev'] in ('cmd','resume','model_issued'):timeline.setdefault(row['k'],[]).append(row)
    cameras=[];q_actual=[];q_parent=[];unrecorded=[];unsent=[]
    try:
        while match.k<=expected['k']:
            for row in timeline.get(match.k,[]):
                if row['ev']=='cmd':match.apply(row['seat'],row['cmd'])
                elif row['ev']=='resume':match.resume()
                else:
                    seq=row['seq'];proof=evidence[seq];recorded=proof['state']
                    if recorded is not None:
                        actual=match.observe('A')
                        for key in ('q','point','score','heard','ball_state','paddle_pos','paddle_normal','base_xy','base_rest'):
                            if key in recorded and actual[key]!=recorded[key]:raise ValueError(f'Public state mismatch seq={seq} key={key}')
                        if proof['worker_input_recorded']:q_actual.append(seq)
                        else:q_parent.append(seq)
                    elif proof['q_unrecorded_canceled']:unrecorded.append(seq)
                    else:raise ValueError('Unqualified missing public state')
                    if proof['canceled_unsent']:unsent.append(seq)
                    saved=a.source/'observations'/f'{seq:05d}.png'
                    if hashlib.sha256(saved.read_bytes()).hexdigest()!=row['image_sha256']:raise ValueError(f'Saved PNG mismatch seq={seq}')
                    view=views.view('A',{'phase':'running','step':match.k,'t_sim':match.k*match.dt,'done':False})
                    png_hash=hashlib.sha256(base64.b64decode(view['observation']['image_png_b64'])).hexdigest()
                    if png_hash!=row['image_sha256']:raise ValueError(f'Native PNG mismatch seq={seq}')
                    cameras.append(seq)
            if match.k==expected['k']:break
            match.step()
        actual_digest=match.state_digest()
        if actual_digest!=expected['digest']:raise ValueError('Final native digest mismatch')
        if len(cameras)!=expected['calls']:raise ValueError('Missing camera checks')
        report={'scope':'Partial development fork only; recorded worker input does not prove server receipt',
                'acceptance':False,'native_digest_exact_match':True,'digest':actual_digest,
                'camera_all':True,'camera_pngs_verified':len(cameras),'q_checks_actual_sent':len(q_actual),
                'q_checks_actual_sent_definition':'Native worker turn/start input.json recorded; no claim of server receipt',
                'q_checks_parent_only':len(q_parent),'canceled_unsent_count':len(unsent),'canceled_unsent_sequences':unsent,
                'q_unrecorded_canceled':unrecorded,'q_unrecorded_canceled_count':len(unrecorded),
                'q_actual_sent_sequences':q_actual,'q_parent_only_sequences':q_parent,
                'all_original_q_verified':not unrecorded,
                'qualified_for_missing_q':bool(unrecorded),'final_step':match.k,'fresh_native_process':True,
                'source_history_sha256':hashlib.sha256((a.source/'episode.jsonl').read_bytes()).hexdigest(),
                'model_calls':0,'api_calls':0}
        output=a.output or a.source/'verified_branch_replay_v2.json'
        with output.open('x') as f:json.dump(report,f,indent=2)
        print(json.dumps(report),flush=True)
        return report
    finally:
        for renderer in sport.worker_call.__globals__.get('_LOCAL',{}).values():renderer.r.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source',type=Path)
    parser.add_argument('--native-root',type=Path,required=True);parser.add_argument('--output',type=Path)
    run(parser.parse_args())
