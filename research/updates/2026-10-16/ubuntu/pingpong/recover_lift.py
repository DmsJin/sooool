"""Optional GPT-selected own-serve recovery; public robot fields only."""
import numpy as np
from arm_ready import ready_command,prep_reply_installed


def eligible(state,ready_q,stance_step,used=False):
    try:
        q=np.asarray(state['q'],float);ready=np.asarray(ready_q,float)
        return bool(not used and state.get('you_serve') and state.get('ball_state')=='your serve'
            and (state.get('serve') or {}).get('phase')=='open' and state.get('ball_in_play') is False
            and ready_command(state) and state['step']-stance_step>=100
            and np.max(np.abs(np.asarray(state['base_rest'])-[.2,-1.87]))<.001
            and q[2:].shape==ready.shape and np.all(np.isfinite(ready))
            and np.max(np.abs(q[2:]-ready))>.1 and state['paddle_pos'][2]<.20
            and state['serve']['deadline_in_s']>=3.2)
    except (KeyError,TypeError,ValueError):return False


def option(state,ready_q,stance_step):
    normal=np.asarray(state['paddle_normal'],float);norm=np.linalg.norm(normal)
    if not np.isfinite(norm) or norm<=0:return None
    p=state['paddle_pos'];normal=normal/norm
    return {'kind':'act','purpose':'recoverlift',
            'description':'Experimental RECOVERY lift, not a ball return: zero blade speed, 2.0 game seconds after execution. May fail to free the arm; do not retoss or replace during this motion.',
            'action':{'type':'act','t':2.0,'pos':[p[0],p[1],max(.35,p[2]+.2)],
                      'normal':normal.tolist(),'vel':[0.,0.,0.],'base':list(state['base_xy']),
                      '_recoverlift_point':state['point'],'_recoverlift_ready_q':list(ready_q),
                      '_recoverlift_seen_step':state['step'],'_recoverlift_stance_step':stance_step}}


def reply_installed(reply,body):
    probe={**body,'_armready_point':body['_recoverlift_point']}
    return prep_reply_installed(reply,probe) and active(reply.get('now',{}),body)


def active(state,body):
    command=state.get('command')
    if state.get('point')!=body.get('_recoverlift_point') or not isinstance(command,dict) or command.get('phase') not in ('approach','follow_through'):return False
    try:
        return all(np.max(np.abs(np.asarray(command[key])-body[key]))<(.0006 if key=='vel' else .0002) for key in ('pos','normal','vel'))
    except (KeyError,TypeError,ValueError):return False


class Recovery:
    def __init__(self):self.installed={}
    def observe(self,records):
        for record in records:
            body=record.get('action',{})
            if record.get('_recoverlift_installed') is True:self.installed[body['_recoverlift_point']]=body
    def blocked(self,state):
        body=self.installed.get(state.get('point'))
        return body is not None and active(state,body)
    def delivery_allowed(self,state,body,records):
        self.observe(records)
        try:
            if body['_recoverlift_point']!=state['point'] or body.get('t')!=2.0 or body['_recoverlift_seen_step']>state['step']:return False
            if not eligible(state,body['_recoverlift_ready_q'],body['_recoverlift_stance_step'],state['point'] in self.installed):return False
            if np.max(np.abs(np.asarray(state['paddle_pos'])[:2]-body['pos'][:2]))>.06:return False
            if np.max(np.abs(np.asarray(state['base_xy'])-body['base']))>.06:return False
            # Any later move away from the serve rest goal invalidates the old settling clock.
            if any(r['step']>body['_recoverlift_stance_step'] and r.get('action',{}).get('type')=='move'
                   and np.max(np.abs(np.asarray(r['action']['base'])-[.2,-1.87]))>=.001 for r in records):return False
            return True
        except (KeyError,TypeError,ValueError):return False
    def mark(self,body,installed):
        if installed and '_recoverlift_point' in body:self.installed[body['_recoverlift_point']]=dict(body)
