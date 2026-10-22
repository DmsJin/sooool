"""Command entrypoint for the selected Asterix experiments."""
import json
import os

from runtime import experiment
from runtime.run_support import ROOT

def asterix(recipe,out,a):
    if getattr(a,'provider',None)=='api':
        from runtime.asterix_api import evaluate
        return evaluate(ROOT,recipe,out,a)
    from runner import run_recipe
    from runtime.subscription import SubscriptionClient
    os.environ['SOL_QUOTA_STOP_PERCENT']=str(min(int(os.environ.get('SOL_QUOTA_STOP_PERCENT','80')),recipe['args']['quota_stop_percent']))
    return run_recipe(ROOT,recipe,out,a,SubscriptionClient,
        mode='realtime' if a.command=='eval' else 'simulation')

def main(argv=None):
    p = experiment.parser("asterix")
    a = p.parse_args(argv)
    a.game = "asterix"
    paid = a.command == 'eval' and a.provider == 'api'
    if a.command == 'eval':
        if a.wall_seconds is not None:
            if a.duration is not None:
                p.error('Use one positive --wall-seconds or --duration')
            a.duration = a.wall_seconds / 5
        if paid:
            if a.max_calls is None:
                a.max_calls = 100
            experiment.validate_budget(p, a)
        elif a.budget_usd is not None or a.ledger is not None or a.max_calls is not None:
            p.error('--budget-usd, --ledger and --max-calls require --provider api')
    if a.duration is not None and round(a.duration*60) < 1:
        p.error('--duration must include at least one game frame')
    recipe = json.loads((a.recipe or ROOT/'recipes/asterix.json').read_text())
    if paid:
        recipe = {**recipe, 'provider': 'openai_api', 'model': 'gpt-6.1-sol', 'effort': 'low',
                  'service_tier': 'ultrafast', 'max_output_tokens': 512}
    mode = ('realtime_api' if paid else 'real_time_subscription') if a.command == 'eval' else 'subscription_with_simulated_profile'
    out, result = experiment.execute(a, recipe, mode, asterix)
    print(json.dumps({'output': str(out), 'result': result}, indent=2))
