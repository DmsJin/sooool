"""Fail closed before spending subscription quota reserved for other work."""
import io
import math
import time


class QuotaGuardError(RuntimeError):
    pass


def summarize_limits(result):
    limits = result.get('rateLimits') or {}
    windows = []
    for name in ('primary', 'secondary'):
        window = limits.get(name)
        if window is None:
            continue
        used = window.get('usedPercent')
        if isinstance(used, bool) or not isinstance(used, (float, int)):
            raise QuotaGuardError('Subscription usage is unavailable')
        if not math.isfinite(used) or not 0 <= used <= 100:
            raise QuotaGuardError('Invalid subscription usage')
        windows.append({'name': name, 'used_percent': used,
                        'window_minutes': window.get('windowDurationMins')})
    if not windows or result.get('ordinaryUsageAllowed') is not True:
        raise QuotaGuardError('Ordinary subscription usage is unavailable; no credit fallback')
    if limits.get('spendControlReached') or limits.get('rateLimitReachedType'):
        raise QuotaGuardError('Subscription limit reached; no credit fallback')
    return {'windows': windows, 'max_used_percent': max(w['used_percent'] for w in windows)}


def read_limits(runner, request_path):
    # Keep account/credit identifiers out of persistent protocol logs.
    with io.StringIO() as log:
        result, _ = runner._rpc('account/rateLimits/read', {}, log,
                                time.monotonic() + 30, request_path)
    return summarize_limits(result)


def require_headroom(summary, stop_percent):
    if summary['max_used_percent'] >= stop_percent:
        raise QuotaGuardError(f'Subscription usage reached reserved threshold {stop_percent}%')
