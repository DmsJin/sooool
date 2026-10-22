"""Command entrypoint for the selected Touhou experiments."""
import json

from runtime import experiment
from runtime.options import credential
from runtime.run_support import ROOT, serve

def touhou(recipe,out,a):
    from research import subscription
    from runtime.subscription import SubscriptionClient
    subscription.SubscriptionClient=SubscriptionClient
    from research.run_episode import run
    config=dict(recipe['args']);config.update(profile=str(ROOT/recipe['profile']),suite=str(ROOT/'vendor'))
    if a.seed is not None:config['seed']=a.seed
    config['browser_executable']=a.browser_executable
    with serve(ROOT/'environments/touhou/dist') as url:
        config['url']=url
        run(config,out/'episode')
    summary=json.loads((out/'episode/summary.json').read_text())
    (out/'summary.json').write_text(json.dumps(summary,indent=2))
    from runtime.touhou_records import evaluation_record
    evaluation_record(ROOT,out)
    return summary

def touhou_realtime(recipe,out,a):
    from research.run_episode import run
    from research.budget import BudgetLedger
    from runtime.touhou_records import evaluation_record
    config=dict(recipe['args'])
    if config.get('speed')!=1:raise ValueError('Realtime acceptance requires speed=1')
    config.update(profile=str(ROOT/recipe['profile']),suite=str(ROOT/'vendor'),
                  ledger=str(a.ledger.resolve() if a.ledger else out/'ledger.json'),
                  max_calls=a.max_calls,browser_executable=a.browser_executable,
                  budget_limits={'total_limit':str(a.budget_usd),'admission_limit':str(a.budget_usd),
                                 'stage_caps':{k:str(a.budget_usd) for k in ('profile','reprofile','realtime')}})
    if a.seed is not None:config['seed']=a.seed
    ledger=BudgetLedger(config['ledger'],**config['budget_limits']);before=ledger.snapshot()
    if before.get('blocked'):raise RuntimeError('Ledger requires reconciliation before new API calls')
    key=credential()
    try:
        with serve(ROOT/'environments/touhou/dist') as url:
            config['url']=url
            result=run(config,out/'episode',key)
        (out/'summary.json').write_text(json.dumps(result,indent=2))
        return result
    finally:
        key=None
        record=evaluation_record(ROOT,out,budget_before=before,budget_after=ledger.snapshot())
        m=json.loads((out/'manifest.json').read_text());m['real_time_api_acceptance']=record['passed']
        (out/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')


def main(argv=None):
    p = experiment.parser("touhou", profiling=True)
    a = p.parse_args(argv)
    a.game = "touhou"
    if a.command in ('eval', 'profile'):
        experiment.validate_budget(p, a)
    if a.command == 'profile':
        from runtime.touhou_profile import profile
        profile(ROOT, a)
        return
    recipe = json.loads((a.recipe or ROOT/'recipes'/('touhou-realtime.json' if a.command == 'eval' else 'touhou.json')).read_text())
    expected = ('api', 'realtime') if a.command == 'eval' else ('subscription', 'sim')
    if (recipe['args'].get('provider'), recipe['args'].get('mode')) != expected:
        p.error('Recipe provider/mode must match the explicitly selected command')
    mode = 'realtime_api' if a.command == 'eval' else 'subscription_with_simulated_profile'
    out, result = experiment.execute(a, recipe, mode, touhou_realtime if a.command == 'eval' else touhou)
    print(json.dumps({'output': str(out), 'result': result}, indent=2))
