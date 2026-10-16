"""Development-only native prefix replay and public camera tracker warmup."""
import base64
import copy
import hashlib
import json


def prefix_before(rows, seq):
    for index, row in enumerate(rows):
        if row['ev']=='model_issued' and row['seq']==seq:
            return rows[:index],row
    raise ValueError('Fork target model_issued missing')


def public_view(source, row):
    text=json.loads((source/f"decision_{row['seq']:05d}/input.json").read_text())['params']['input'][0]['text']
    state=json.loads(text.split('\nSTATE ',1)[1].split('\nIMAGE_META ',1)[0])
    meta=json.loads(text.split('\nIMAGE_META ',1)[1].split('\nCANDIDATES ',1)[0])
    png=(source/'observations'/f"{row['seq']:05d}.png").read_bytes()
    if hashlib.sha256(png).hexdigest()!=row['image_sha256']:
        raise ValueError('Fork saved camera hash mismatch')
    return {'state':state,'observation':{**meta,'image_png_b64':base64.b64encode(png).decode()}}


def replay_prefix(match, prefix, target, ep):
    for row in prefix:
        if row['ev'] not in ('cmd','resume'):continue
        while match.k<row['k']:match.step()
        if match.k!=row['k']:raise ValueError('Fork prefix order mismatch')
        if row['ev']=='cmd':match.apply(row['seat'],row['cmd'])
        else:match.resume()
        ep.write(row['ev'],**{k:v for k,v in row.items() if k not in ('ev','ts','wall')})
    while match.k<target['k']:match.step()
    if match.k!=target['k']:raise ValueError('Fork target clock mismatch')


def prefix_actions(prefix,dt=.01):
    """Recover only already-effected own actions; never index beyond cutoff."""
    issued={};visible={};counts={};actions={};bundle_starts={}
    for index,row in enumerate(prefix):
        if row['ev']=='model_issued':issued[row['seq']]=row
        elif row['ev']=='model_visible':visible[row['seq']]=row
        elif row['ev']=='cmd':
            if row['seat']!='A':raise ValueError('High replay supports own A commands only')
            if index+1>=len(prefix) or prefix[index+1]['ev']!='effect':
                raise ValueError('High replay command lacks adjacent completed effect before cutoff')
            effect=prefix[index+1];seq=effect['seq']
            if effect['k']!=row['k']:raise ValueError('High replay effect clock mismatch')
            if seq not in issued or seq not in visible:
                raise ValueError('High replay missing already-visible original choice')
            selected=issued[seq]['options'][json.loads(visible[seq]['answer'])['choice']]
            count=counts.get(seq,0);counts[seq]=count+1
            if selected['kind']=='serve_bundle':
                if count>=len(selected['actions']):raise ValueError('Too many bundle effects')
                body=copy.deepcopy(selected['actions'][count]['action'])
                if count==0:bundle_starts[seq]=row['k']
                elif row['k']<bundle_starts[seq]+selected['actions'][count]['after_steps']:
                    raise ValueError('High replay serve bundle ran before scheduled time')
            elif selected['kind'] in ('act','move','abort_stroke') and count==0:
                body=copy.deepcopy(selected['action'])
            else:raise ValueError('Unsupported high replay historical option: '+selected['kind'])
            if body['type']=='act':
                rounded_remaining=float(effect['info']['T_from_now'])
                if selected.get('contact_step') is not None:
                    ticks=selected['contact_step']-row['k']
                    if int(ticks)!=ticks:raise ValueError('High replay noninteger contact step')
                    body['t']=int(ticks)*dt
                elif 't' not in body:
                    raise ValueError('High replay act lacks exact original time or absolute contact')
                if round(body['t'],4)!=rounded_remaining:
                    raise ValueError('High replay rounded contact evidence mismatch')
            actions[index]={'body':body,'effect':effect,'seq':seq,'k':row['k']}
    return actions


def verify_public_observation(source,row,match,views,check_command=True):
    recorded=public_view(source,row)
    actual=match.observe('A')
    keys=['q','point','score','heard','ball_state']
    if check_command:keys+=['command','base_rest']
    for key in keys:
        if actual[key]!=recorded['state'][key]:
            raise ValueError('High replay public state mismatch: '+key+' seq='+str(row['seq']))
    view=views.view('A',{'phase':'running','step':match.k,'t_sim':match.k*match.dt,'done':False})
    digest=hashlib.sha256(base64.b64decode(view['observation']['image_png_b64'])).hexdigest()
    if digest!=row['image_sha256']:raise ValueError('High replay camera mismatch seq='+str(row['seq']))
    return digest


def replay_high_prefix(source,match,layer,prefix,target,views,ep,parse_action,applied):
    from action_feedback import public_feedback
    actions=prefix_actions(prefix,match.dt)
    verified=0
    for index,row in enumerate(prefix):
        if row['ev'] not in ('cmd','resume','model_issued'):continue
        while match.k<row['k']:match.step()
        if match.k!=row['k']:raise ValueError('High replay prefix order mismatch')
        if row['ev']=='model_issued':
            verify_public_observation(source,row,match,views);verified+=1
        elif row['ev']=='resume':
            match.resume()
            ep.write('resume',**{k:v for k,v in row.items() if k not in ('ev','ts','wall')})
        else:
            item=actions[index];body=item['body'];expected=item['effect']
            cmd=parse_action(layer,'A',body,match,{})
            low,info=layer.lower('A',cmd,None,match)
            if low!=row['cmd']:raise ValueError('High replay low command mismatch seq='+str(item['seq']))
            if info!=expected['info']:raise ValueError('High replay planner feedback mismatch seq='+str(item['seq']))
            result=match.apply('A',low)
            if result!=expected['result']:raise ValueError('High replay installed result mismatch seq='+str(item['seq']))
            point=match.observe('A')['point']
            applied.append({'step':match.k,'seq':item['seq'],'point':point,'action':body,
                            'execution_feedback':public_feedback(info)})
            ep.write('cmd',**{k:v for k,v in row.items() if k not in ('ev','ts','wall')})
            ep.write('effect',**{k:v for k,v in expected.items() if k not in ('ev','ts','wall')})
    while match.k<target['k']:match.step()
    if match.k!=target['k']:raise ValueError('High replay target clock mismatch')
    verify_public_observation(source,target,match,views)
    return verified+1


def setup(source,seq,match,views,menu,timing,ep,*,high_layer=None,parse_action=None,reference_factory=None,applied=None):
    history=source/'episode.jsonl'
    rows=[json.loads(line) for line in history.read_text().splitlines()]
    prefix,target=prefix_before(rows,seq)
    high_checks=None
    if high_layer is None:
        replay_prefix(match,prefix,target,ep)
    else:
        if reference_factory is None or parse_action is None or applied is None:
            raise ValueError('High replay requires reference factory, parser and applied output')
        count=replay_high_prefix(source,match,high_layer,prefix,target,views,ep,parse_action,applied)
        class Silent:
            def write(self,*args,**kwargs):pass
        reference=reference_factory()
        replay_prefix(reference,prefix,target,Silent())
        native_digest=match.state_digest()
        if native_digest!=reference.state_digest():raise ValueError('High/low replay native digest mismatch')
        del reference
        high_checks={'historical_public_observations_and_png_verified':count,
                     'low_commands_feedback_results_exact':True,'public_target_command_exact':True,
                     'high_low_native_digest_exact':True,'native_digest':native_digest,
                     'source_cutoff_digest_available':False,
                     'limitation':'Digest compared to independent original-low-command replay; source has no recorded cutoff digest',
                     'restored_applied_count':len(applied)}
    recorded=public_view(source,target)
    actual=match.observe('A')
    for key in ('q','point','score','heard','ball_state'):
        if actual[key]!=recorded['state'][key]:raise ValueError('Fork public state mismatch: '+key)
    view=views.view('A',{'phase':'running','step':match.k,'t_sim':match.k*match.dt,'done':False})
    digest=hashlib.sha256(base64.b64decode(view['observation']['image_png_b64'])).hexdigest()
    if digest!=target['image_sha256']:raise ValueError('Fork actual camera hash mismatch')
    if menu is None:raise ValueError('Fork requires public camera candidate mode')
    warmed=0
    for row in prefix:
        if row['ev']=='model_issued':
            menu.build(copy.deepcopy(public_view(source,row)),timing)
            warmed+=1
    provenance={'source':str(source),'source_history_sha256':hashlib.sha256(history.read_bytes()).hexdigest(),
                'target_seq':seq,'target_step':target['k'],'camera_sha256':digest,'public_frames_warmed':warmed,
                'old_model_results_used':False,'acceptance':False,'include_in_scores':False}
    if high_checks is not None:
        provenance.update(high_replay=high_checks,old_model_results_used=True,
                          old_model_results_scope='already-applied original prefix choices only; no post-cutoff answer')
    ep.write('fork_start',k=match.k,**provenance)
    return provenance
