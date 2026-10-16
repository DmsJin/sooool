"""Opt-in GPT cancellation menu from matched public own-plan rehearsal only."""
import math


def dangerous_stroke(state):
    """Return matched record and reasons; never infer a real physical collision."""
    command = state.get('command')
    if (state.get('ball_state') != 'coming to you' or not state.get('ball_in_play')
            or (state.get('you_serve') and (state.get('serve') or {}).get('phase') != 'done')
            or not isinstance(command, dict)
            or command.get('phase') != 'approach'):
        return None
    try:
        lead = float(command['contact_in_s'])
        if not math.isfinite(lead) or lead <= 0:
            return None
        record = next((r for r in reversed(state.get('recent_applied', []))
                       if r.get('action', {}).get('type') == 'act'), None)
        if record is None or record.get('point') != state['point']:
            return None
        action = record['action']
        contact = state['step'] + lead / .01
        recorded_contact = record['step'] + float(action['t']) / .01
        if not math.isfinite(recorded_contact) or abs(recorded_contact - contact) > 1 + 1e-8:
            return None
        for key in ('pos', 'normal', 'vel'):
            a, b = action[key], command[key]
            if len(a) != 3 or len(b) != 3:
                return None
            if key == 'normal':
                norm = math.sqrt(sum(float(x) ** 2 for x in a))
                if not math.isfinite(norm) or norm <= 0:
                    return None
                a = [float(x) / norm for x in a]
            delta = [float(x) - float(y) for x, y in zip(a, b)]
            tolerance = 5.1e-4 if key == 'vel' else 2e-4
            if not all(math.isfinite(x) for x in delta) or max(map(abs, delta)) > tolerance:
                return None
        feedback = record.get('execution_feedback', {})
        reasons = []
        if feedback.get('table_contact_in_rehearsal') is True:
            reasons.append('table contact in rehearsal')
        blade = float(feedback.get('blade_error_m', 0))
        scale = float(feedback.get('speed_scale', 0))
        if math.isfinite(blade) and math.isfinite(scale) and blade > .05 and scale > 4:
            reasons.append('blade error > .05 m and speed scale > 4')
        return (record, reasons) if reasons else None
    except (KeyError, TypeError, ValueError, StopIteration):
        return None


def abort_option(state, option_id):
    matched = dangerous_stroke(state)
    if matched is None:
        return None
    record, reasons = matched
    return {'id': option_id, 'kind': 'abort_stroke',
            'description': 'Cancel this dangerous incoming stroke and return to ready; may concede this ball',
            'action': {'type': 'none', '_abortstroke_point': state['point'],
                       '_abortstroke_step': record['step']},
            'rehearsal_warning': reasons,
            'limitation': 'Predicted own-plan feedback, not evidence of an actual collision or guaranteed recovery'}


def eligible_at_delivery(state, body):
    matched = dangerous_stroke(state)
    return bool(matched and body.get('_abortstroke_point') == state['point']
                and body.get('_abortstroke_step') == matched[0]['step'])


class AbortLifecycle:
    """Block in-flight decisions made before a confirmed clear, within that point."""
    def __init__(self):
        self.point = None
        self.step = None

    def installed(self, body, point, step, confirmed):
        if (confirmed and body.get('type') == 'none'
                and body.get('_abortstroke_point') == point):
            self.point, self.step = point, step

    def stale_act(self, body, point, seen):
        return (body.get('type') == 'act' and self.step is not None
                and point == self.point and seen <= self.step)
