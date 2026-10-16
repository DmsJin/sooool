"""GPT-selected observation gates using only public referee fields.
This helper can wake observation; it never selects or executes game actions.
"""
def make_watch(option,point,step):
 rule=option.get('watch_for')
 if rule is None:return None
 if rule.get('ball_state')!='coming to you' or rule.get('require_in_play') is not True:raise ValueError('Unsupported public observation gate')
 maximum=rule['max_steps']
 if type(maximum)!=int or not 1<=maximum<=100:raise ValueError('Invalid watch duration')
 return {'point':point,'deadline':step+maximum}

def wake_reason(watch,state,step):
 if state.get('point')!=watch['point']:return 'point_changed'
 if state.get('ball_in_play') and state.get('ball_state')=='coming to you':return 'incoming_public_referee'
 if step>=watch['deadline']:return 'maximum_wait_elapsed'
 return None
