"""Single direct high action I/O. Standard library only; never predicts the ball.

Bounds mirror public action_high.py, rcb_tt.py and serve.py on this revision.
Parsing is static validation; the native service judges state-dependent legality,
reach, timing and execution. ``wait`` means do not submit an /act request.
"""
import json
import math


STATE_FIELDS = frozenset('phase done reason ready world step t_sim score point ball '
    't_since_played you_serve you_receive_serve serve heard q base_xy paddle_pos '
    'paddle_normal ball_in_play ball_state points shots command base_rest retired'.split())
SPEC_FIELDS = frozenset('protocol action_level actions action_schema robot arm_limits base '
    'base cameras image image_layout frame serve calls match timing'.split())
IMAGE_FIELDS = frozenset('view_times view_steps view_leg_ids view_sim_times image_layout'.split())
TIMING_FIELDS = frozenset('p50_wall_s p95_wall_s p50_game_s p95_game_s slowdown '
    'virtual_model_capacity observation_interval_game_s delay_source profile'.split())
FEEDBACK_FIELDS = frozenset('stroke n_swing_steps_available n_swing_steps ik_residual '
    'blade_error_m normal_error_deg speed_scale base base_goal approach '
    'table_contact_in_rehearsal paddle_vel_delivered T_from_now'.split())

BASE = '''You control a table-tennis robot. Win the match using the actual attached
camera image and public own-state/referee information. Only images reveal the ball;
do not assume unobserved ball or opponent coordinates. Read native SPEC for camera
geometry, image chronology, frame, rules and robot limits. No action menu is supplied.
Output exactly one JSON object, no prose or markdown, using one of these forms:
{"type":"wait"}
{"type":"move","base":[x,y]}
{"type":"toss","pos":[x,y,z],"height":h}
{"type":"act","t":T,"pos":[x,y,z],"normal":[nx,ny,nz],"vel":[vx,vy,vz]}
{"type":"none"}
An act may also include optional "base":[bx,by]. No other fields or actions.
wait leaves the current command intact; the controller later observes again.
none explicitly cancels a stroke and returns the arm to ready. move sets the base
rest goal. toss is only for your legal service. act requests blade centre, face
normal and velocity at contact; native IK, swing planning, speed limits, physics,
rehearsal and execution scatter remain in force. A new act replaces a pending act.
Use metres, seconds and m/s. Base: -1<=x<=1, -2.4<=y<=-1.5.
Act: 0<T<=2.5; -2<=x<=2, -3.3<=y<=-.3, -.5<=z<=1.5;
normal must be nonzero (prefer a unit vector); velocity norm <=8.
Toss: .16<=height<=1, y<=-1.39, .02<=z<=.9 and within .9m
of the actual base horizontally. Native service also judges phase and legality.
The act time T is relative to actual command EFFECT, not this image or request.
The world advances during preprocessing, model response and native execution.
Future delay is unknown: do not assume an exact response/effect step. Public
latency statistics, if supplied, are estimates, not the pending request's delay.
Choose the action yourself from the observed game; no automatic strike follows.
'''


def _pick(value, fields):
    return {key: value[key] for key in sorted(fields) if key in value}


def prompt(view, spec, timing=None, variant='direct_v1'):
    """Text alongside the *original* raw PNG; this function never reads pixels.

    Explicit allowlists omit legacy menu/fit/stance/known-plan additions. The caller
    attaches view['observation']['image_png_b64'] unchanged as an image input.
    """
    if variant not in ('direct_v1', 'direct_latency_v1', 'direct_feedback_v1'):
        raise ValueError('Unknown direct variant')
    state = _pick(view['state'], STATE_FIELDS)
    extra = ''
    if variant == 'direct_latency_v1':
        extra = '\nConsider the supplied latency range when choosing time and movement.\n'
    elif variant == 'direct_feedback_v1':
        extra = ('\nPublic own execution feedback is a planner rehearsal prediction, '
                 'not actual ball contact or ball outcome. Compare it with later real images.\n')
        feedback = []
        for record in view['state'].get('recent_applied', []):
            item = _pick(record, {'step', 'point'})
            if isinstance(record.get('execution_feedback'), dict):
                item['execution_feedback'] = _pick(record['execution_feedback'], FEEDBACK_FIELDS)
                feedback.append(item)
        state['recent_execution_feedback'] = feedback
    payload = [('TIMING', _pick(timing or {}, TIMING_FIELDS)),
               ('SPEC', _pick(spec, SPEC_FIELDS)), ('STATE', state),
               ('IMAGE_META', _pick(view.get('observation', {}), IMAGE_FIELDS))]
    return BASE + extra + ''.join('\n' + name + ' ' + json.dumps(value,
        separators=(',', ':'), allow_nan=False) for name, value in payload)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON constant: ' + value)


def _number(value):
    if type(value) not in (int, float):
        raise ValueError('Expected a finite number, not a bool/string')
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError('Expected a finite number')
    return value


def _vector(value, length):
    if type(value) is not list or len(value) != length:
        raise ValueError('Expected a numeric vector of length ' + str(length))
    for item in value:
        _number(item)
    return value


def _base(value):
    x, y = _vector(value, 2)
    if not (-1 <= x <= 1 and -2.4 <= y <= -1.5):
        raise ValueError('Base outside native travel')


def parse(text):
    """Validate one complete direct action; all invalid outputs raise ValueError.

    Returns the original numeric values, without clipping, normalization, inferred
    timing, action substitution or state-dependent automatic control.
    """
    if type(text) is not str:
        raise ValueError('Expected JSON text')
    try:
        body = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError('Expected one complete JSON action') from exc
    if type(body) is not dict or type(body.get('type')) is not str:
        raise ValueError('Expected a direct action object')
    kind = body['type']
    required = {'wait': {'type'}, 'none': {'type'}, 'move': {'type', 'base'},
                'toss': {'type', 'pos', 'height'},
                'act': {'type', 't', 'pos', 'normal', 'vel'}}
    if kind not in required:
        raise ValueError('Unsupported action type')
    allowed = required[kind] | ({'base'} if kind == 'act' else set())
    if not required[kind] <= body.keys() or not body.keys() <= allowed:
        raise ValueError('Missing or extra action fields')
    if 'base' in body:
        _base(body['base'])
    if kind == 'act':
        t = _number(body['t'])
        x, y, z = _vector(body['pos'], 3)
        normal = _vector(body['normal'], 3)
        velocity = _vector(body['vel'], 3)
        if not 0 < t <= 2.5:
            raise ValueError('Act t outside (0,2.5]')
        if not (-2 <= x <= 2 and -3.3 <= y <= -.3 and -.5 <= z <= 1.5):
            raise ValueError('Act pos outside native bounds')
        norm = math.hypot(*normal)
        if not math.isfinite(norm) or norm < 1e-6:
            raise ValueError('Act normal must be finite and nonzero')
        if math.hypot(*velocity) > 8:
            raise ValueError('Act velocity exceeds native limit')
    elif kind == 'toss':
        x, y, z = _vector(body['pos'], 3)
        height = _number(body['height'])
        # Union of the public base travel plus toss reach; actual-base reach and
        # serve phase are checked by native code, not invented by this parser.
        if not (-1.9 <= x <= 1.9 and -3.3 <= y <= -1.39 and .02 <= z <= .9):
            raise ValueError('Toss point outside public legal/device envelope')
        if not .16 <= height <= 1:
            raise ValueError('Toss height outside native limits')
    return body
