"""Explicit optional GPT preparation action; public own-state gates only."""
import numpy as np


def ready_command(state):
    if 'command' not in state:return False
    command=state['command']
    return (command is None or isinstance(command,str) and command.startswith('none')
            or isinstance(command,dict) and command.get('phase')=='ready')


def prepared_in_point(state,records):
    return any(record.get('action',{}).get('_armready_point')==state.get('point') for record in records)


def eligible(state,records):
    return (state.get('ball_state')=='going to the opponent' and state.get('ball_in_play') is True
            and ready_command(state) and not prepared_in_point(state,records))


def preparation(state,bundle=False):
    normal=np.array([.15,.86,.49]);normal=normal/np.linalg.norm(normal)
    action={'type':'act','t':.6,'pos':[0.,-1.18,.22],'normal':normal.tolist(),
            'vel':[0.,0.,0.],'base':[0.,-1.67],'_armready_point':state['point']}
    result={'kind':'act','purpose':'armready','contact_step':state['step']+60,'lead_game_s':.6,
            'description':'Experimental ARM PREPARATION, not a return: move to a fixed receive pose at zero blade speed. '
                          'The pose is over your half of the table; outgoing status cannot guarantee the ball has cleared it. '
                          'Choose only when the actual camera shows safe clearance. Native motion later returns to ready.',
            'armready':{'fixed_design':True,'ball_path_clearance_guaranteed':False,'automatic_action':False},
            'action':action}
    if bundle:
        result['kind']='armready_bundle'
        result['description']+=' After it takes effect, set receive base_rest to -1.67 without cancelling the swing.'
        result['actions']=[{'after_steps':0,'action':result.pop('action')},
                           {'after_steps':0,'action':{'type':'move','base':[0.,-1.67],
                                                    '_armready_followup_point':state['point']}}]
    return result


def bundle_first(option,step):
    body=dict(option['actions'][0]['action'])
    body['t']=(option['contact_step']-step)*.01
    return body if body['t']>=.04 else None


def bundle_followups(option,effect_step,point,seq,seen):
    if effect_step is None or option['actions'][0]['action']['_armready_point']!=point:return []
    return [{'due':effect_step+c['after_steps'],'action':dict(c['action']),'point':point,'seq':seq,'seen':seen}
            for c in option['actions'][1:]]


def installed_prep_step(low,result,step):
    return step if low.get('type')=='traj' and result.get('command')=='traj' and not result.get('rejected') else None


def prep_reply_installed(reply,body):
    """Require both successful public stroke feedback and its active own command."""
    if reply.get('http_status'):return False
    effect=reply.get('took_effect',{});stroke=effect.get('stroke',{});state=reply.get('now',{})
    command=state.get('command')
    if state.get('point')!=body['_armready_point'] or not isinstance(command,dict):return False
    try:
        return (stroke['n_swing_steps']>0 and np.linalg.norm(np.asarray(command['pos'])-body['pos'])<2e-4
                and np.linalg.norm(np.asarray(command['normal'])-body['normal'])<2e-4
                and abs(effect['step']+body['t']/.01-state['step']-command['contact_in_s']/.01)<=1.01)
    except (KeyError,TypeError,ValueError):return False
