"""Opt-in control-input context; never computes entity positions or actions."""
import json


def validate_known_plan_feedback(config):
    enabled=config.get('known_plan_feedback',False)
    if type(enabled) is not bool:
        raise ValueError('known_plan_feedback must be boolean')
    if enabled and (type(config.get('decision_fanout',1)) is not int
                    or config.get('decision_fanout',1)!=1
                    or config.get('wait_for_winner') is not True
                    or config.get('wait_for_move') is not False
                    or config.get('rolling_observations',False) is not False):
        raise ValueError('known_plan_feedback requires K1, wait_for_winner=true, wait_for_move=false, rolling_observations=false')
    return enabled


def captured_control_context(observation):
    clock=observation.get('clock')
    fields=('frame','visual_frame','held','remaining','active_plan','pending_plan')
    if not isinstance(clock,dict) or any(field not in clock for field in fields):
        raise ValueError('known_plan_feedback requires complete atomic capture clock control metadata')
    # Whitelist only public clocks and previously returned GPT controls.
    context={field:clock[field] for field in fields}
    for field in ('frame','visual_frame','remaining'):
        if type(context[field]) is not int or context[field]<0:
            raise ValueError('Invalid capture control clock '+field)
    held=context['held']
    if not isinstance(held,list) or len(held)!=4 or any(type(v) is not int for v in held):
        raise ValueError('Invalid capture held controls')
    if held[0] not in range(9) or any(v not in (0,1) for v in held[1:]):
        raise ValueError('Invalid capture held controls')
    pending=context['pending_plan']
    if not isinstance(pending,list):raise ValueError('Missing queued control suffix')
    for row in pending:
        if (not isinstance(row,list) or len(row)!=5 or any(type(v) is not int for v in row)
                or row[0] not in range(9) or any(v not in (0,1) for v in row[1:4]) or not 1<=row[4]<=120):
            raise ValueError('Invalid queued control suffix')
    active=context['active_plan']
    if context['remaining']:
        if (not isinstance(active,dict) or set(active)!= {'action','start','end'}
                or active['action']!=held or type(active['start']) is not int or type(active['end']) is not int
                or not 0<=active['start']<=context['frame']
                or active['end']!=context['frame']+context['remaining']):
            raise ValueError('Invalid active control schedule')
    elif active is not None:raise ValueError('Expired active control schedule must be null')
    # Roundtrip also rejects non-JSON values/nonfinite metadata, without repairs.
    return json.loads(json.dumps(context,allow_nan=False))


def observation_gate_open(config,clock,capacity_available,lastissued,latest_observation,pending):
    """Existing runner gates, shared with offline protocol invariant tests."""
    available=capacity_available
    if config.get('wait_for_winner') and lastissued>=0 and latest_observation<lastissued:
        if pending(lastissued):available=False
    if config.get('wait_for_move') and (clock['held'][0]!=0 or any(a[0]!=0 for a in clock.get('pending_plan',[]))):
        available=False
    return available


KNOWN_PLAN_PROTOCOL = ("Controller protocol: K1 winner-gated known-plan feedback. A new request is submitted only after the preceding request has applied a legal plan or finished invalid. This screenshot may be captured while that already returned plan is still executing. Only this observation is awaiting an unapplied answer; no other unknown model answer can change your controls before yours. The captured active action and queued suffix continue in logical-frame order until they finish, then movement and X release while Z/Shift persist. Your new answer replaces any unfinished suffix when it arrives. Use the capture logical frame, remaining duration and complete known schedule to estimate your control starting point yourself. Death, respawn, boundaries and cinematic freezes can invalidate simple displacement prediction. No future game state or this request's sampled delay is supplied.\n")
