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

def schedule_wait(wake,watch,option,point,step,*,latest=False,legacy_empty_updates=False):
 """Schedule an already accepted wait; callers retain their sequence/point guards.

 Latest mode replaces only observation timing/gates, never a committed stroke.
 legacy_empty_updates preserves the realtime zero-duration wait behavior, which
 historically differs from the simulation's no-op zero-duration wait.
 """
 gate=make_watch(option,point,step)
 if latest:return step+option.get('wait_steps',0),gate
 if option.get('wait_steps') or legacy_empty_updates:
  wake=max(wake,step+option.get('wait_steps',0))
 return wake,gate if gate is not None else watch

def wake_reason(watch,state,step):
 if state.get('point')!=watch['point']:return 'point_changed'
 if state.get('ball_in_play') and state.get('ball_state')=='coming to you':return 'incoming_public_referee'
 if step>=watch['deadline']:return 'maximum_wait_elapsed'
 return None
