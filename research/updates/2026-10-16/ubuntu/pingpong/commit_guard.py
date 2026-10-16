"""Narrow optional replacement filter from public own-command feedback only."""
import numpy as np


def angle(a,b):
    a=np.asarray(a,float);b=np.asarray(b,float)
    denom=np.linalg.norm(a)*np.linalg.norm(b)
    return float(np.degrees(np.arccos(np.clip(np.dot(a,b)/denom,-1,1)))) if denom>0 else float('inf')


def filter_replacements(state,options,normal_limit=2):
    meta={'reason':'no verified good active incoming stroke','removed_count':0,'normal_shift_limit_deg':normal_limit}
    state['commit_guard']=meta
    command=state.get('command')
    if state.get('ball_state')!='coming to you' or not state.get('ball_in_play') or not isinstance(command,dict) or command.get('phase')!='approach':
        return options
    try:
        contact=state['step']+float(command['contact_in_s'])/.01
        matched=None
        for record in reversed(state.get('recent_applied',[])):
            action=record.get('action',{})
            if action.get('type')!='act' or record.get('point')!=state['point']:continue
            if abs(record['step']+float(action['t'])/.01-contact)>1+1e-8:continue
            if np.linalg.norm(np.asarray(action['pos'])-np.asarray(command['pos']))>2e-4:continue
            if angle(action['normal'],command['normal'])>.05:continue
            matched=record
            break
        if matched is None:return options
        feedback=matched.get('execution_feedback',{})
        values=[float(feedback[key]) for key in ('blade_error_m','normal_error_deg','speed_scale')]
        if not all(np.isfinite(v) and v>=0 for v in values):return options
        if values[0]>.015 or values[1]>2.5 or values[2]>2 or feedback.get('table_contact_in_rehearsal') is not False:return options
        kept=[]
        for option in options:
            remove=False
            if option['kind']=='act':
                action=option['action'];step=option['contact_step']
                remove=((step-state['step'])*.01<.55 and abs(step-contact)*.01<=.02+1e-8
                        and np.linalg.norm(np.asarray(action['pos'])-np.asarray(command['pos']))<=.015
                        and angle(action['normal'],command['normal'])<=normal_limit)
            if not remove:kept.append(option)
        meta.update(reason='preserve verified good stroke against small late replacements',removed_count=len(options)-len(kept))
        for index,option in enumerate(kept):option['id']=index
        return kept
    except (KeyError,TypeError,ValueError):
        return options


def preserve_at_delivery(state,body,contact_step=None,normal_limit=2):
    """Recheck a GPT-selected action against fresh public feedback; never send a replacement.

    The optional 15-degree experiment protects orientation changes at an otherwise
    unchanged contact; it is a causal ablation, not general evidence of safety.
    """
    if body.get('type')!='act':return False
    if contact_step is None:contact_step=state['step']+float(body['t'])/.01
    option={'id':0,'kind':'act','action':body,'contact_step':contact_step}
    return not filter_replacements(state,[option],normal_limit=normal_limit)
