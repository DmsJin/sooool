"""Auditable evaluation records; model decisions and evaluator truth stay separate."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def evaluation_record(root, out, *, budget_before=None, budget_after=None):
    out=Path(out);episode=out/'episode'
    manifest=json.loads((out/'manifest.json').read_text())
    summary=json.loads((episode/'summary.json').read_text()) if (episode/'summary.json').exists() else {'complete':False,'status':'interrupted'}
    actions=rows(episode/'actions.jsonl');decisions=rows(episode/'decisions.jsonl')
    mode='saved_action_replay' if summary.get('replayed_calls',0) else manifest['mode'];is_api=mode=='realtime_api'
    integrity=bool(summary.get('complete') and not summary.get('validation_failure') and (not is_api or summary.get('terminal_accounting_complete')))
    final=json.loads((episode/'final_state.json').read_text()) if (episode/'final_state.json').exists() else {}
    clocks=[a.get('apply_clock',{}) for a in actions]+[final.get('clock',{})]
    clock_verified=bool(clocks) and all(c.get('mode')=='realtime' and c.get('speed')==1 and c.get('paused') is False and c.get('blur_events',0)==0 for c in clocks)
    if is_api:integrity=integrity and clock_verified
    delays=[a['capture_to_apply_s'] for a in actions if a.get('capture_to_apply_s') is not None] if is_api else []
    policy=Path(root)/'policies/touhou/tracking-safe-intercept-v2/policy.txt'
    engine=Path(root)/'environments/touhou/dist/engine.mjs'
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=root,text=True,capture_output=True).stdout.strip() or None
    accounting=None
    if budget_after is not None:
        from decimal import Decimal
        previous=set((budget_before or {}).get('requests',{}))
        entries=[e for rid,e in budget_after['requests'].items() if rid not in previous and e.get('owner_pid')==os.getpid()]
        settled=all(e['status']=='settled' for e in entries)
        accounting={'requests_billed':len(entries),'settled':settled,'usd':str(sum((Decimal(e['actual_usd']) for e in entries if e['status']=='settled'),Decimal(0))),
                    'ledger_committed_usd':budget_after['committed_usd'],'unknown_usage':not settled,'blocked':budget_after.get('blocked')}
        integrity=integrity and settled and not accounting['blocked']
    record={'schema_version':1,'record_id':out.name,'game':'touhou','policy':'tracking-safe-intercept-v2',
            'policy_sha256':hashlib.sha256(policy.read_bytes()).hexdigest(),'engine_sha256':hashlib.sha256(engine.read_bytes()).hexdigest(),
            'source_commit':commit,'provenance':'package_cli','execution_mode':mode,'model':'gpt-6.1-sol','effort':'low',
            'clock_1x_verified':clock_verified if is_api else None,'final_clock':final.get('clock'),
            'seed':summary.get('seed',manifest['recipe']['args'].get('seed')),'fanout':manifest['recipe']['args'].get('decision_fanout'),
            'public_summary_language':manifest['recipe']['args'].get('brief_language'),'complete':bool(summary.get('complete')),
            'integrity_verified':integrity,'won':bool(summary.get('won')),'passed':bool(is_api and summary.get('won') and integrity),
            'status':summary.get('status'),'game_s':summary.get('game_s'),'hits':summary.get('hits'),'boss_hp':summary.get('boss_hp'),
            'replayed_calls':summary.get('replayed_calls',0),'calls_issued':summary.get('calls',len(decisions)),'actions_applied':len(actions),
            'latency':{'scope':'actual screenshot capture to mechanical action application','samples':len(delays),'median_s':statistics.median(delays) if delays else None,'min_s':min(delays) if delays else None,'max_s':max(delays) if delays else None} if is_api else None,
            'accounting':accounting,'evidence':{'manifest':'manifest.json','summary':'episode/summary.json','requests':'episode/issued.jsonl','decisions':'episode/decisions.jsonl','actions':'episode/actions.jsonl','video':'episode/video/' if is_api else None},
            'acceptance_note':'Only won + uninterrupted 1x API + terminal accounting is real-time acceptance. Survival, replay, and profile simulation are distinct outcomes.'}
    (out/'record.json').write_text(json.dumps(record,indent=2)+'\n')
    return record
