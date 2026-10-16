"""Strict historical execution timing versus genuinely new resumed chunk effects."""
import math


def terminal_step(summary,rows):
    step=summary.get('k')
    ends=[r for r in rows if r.get('ev')=='end']
    if (type(step)!=int or step<0 or len(ends)!=1
            or type(ends[0].get('k'))!=int or ends[0]['k']!=step):
        raise ValueError('Resume summary/end terminal step mismatch')
    if not rows or rows[-1].get('ev')!='end' or any(r.get('k',step)>step for r in rows):
        raise ValueError('Resume history extends beyond terminal step')
    return step


def execution_cost(step,seq,cutoff,source_terminal,blocks,actual,slowdown,dt):
    if seq>=cutoff:return actual,None,None
    old=blocks.get((step,seq))
    if old is not None:
        elapsed=old.get('elapsed_wall_s')
        if (type(elapsed) not in (int,float) or not math.isfinite(elapsed) or elapsed<0
                or old.get('k')!=step or old.get('seq')!=seq
                or old.get('until')!=step+max(0,math.ceil(elapsed/slowdown/dt))):
            raise ValueError('Invalid cached execution block timing')
        return elapsed,actual,None
    if source_terminal is None or step<=source_terminal:
        raise ValueError('Missing cached execution block')
    return actual,None,{'source_terminal_step':source_terminal,'cached_choice_seq':seq,
                        'effect_step':step,'cost_source':'fresh measured lowering/apply',
                        'reason':'new chunk effect after original terminal step'}


def retry_delay(stderr,summary,attempt):
    """Bounded same-episode recovery only; never retry structural/numeric failures."""
    if attempt>=2:return None
    text=(stderr+'\n'+str(summary.get('failure',''))).lower()
    if any(marker in text for marker in ('quota','usage limit','usage_limit','mismatch',
                                         'replay','cached execution block','numerical',
                                         'nonfinite','non-finite','nan','infinity')):
        return None
    worker_exit='RuntimeError: Subscription worker exited; inspect native stderr; no paid fallback'
    if (summary.get('failure')==worker_exit
            and 'TimeoutError: codex did not finish this request' in stderr):return 2
    if 'serverOverloaded' in stderr or 'Selected model is at capacity' in stderr:return 60
    return None
