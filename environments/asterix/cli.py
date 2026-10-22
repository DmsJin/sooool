"""Command entrypoint for the selected Asterix experiments."""
import json
import math
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
    if a.command == "doctor":
        return experiment.doctor(a)
    paid = a.command == 'eval' and a.provider == 'api'
    if a.command == 'eval':
        if a.wall_seconds is not None:
            if a.duration is not None or not math.isfinite(a.wall_seconds) or a.wall_seconds <= 0:
                p.error('Use one positive --wall-seconds or --duration')
            a.duration = a.wall_seconds / 5
        if paid:
            experiment.validate_budget(p, a)
    if a.duration is not None and (not math.isfinite(a.duration) or a.duration <= 0 or round(a.duration*60) < 1):
        p.error('--duration must be finite and positive')
    recipe = json.loads((a.recipe or ROOT/'recipes/asterix.json').read_text())
    if paid:
        recipe = {**recipe, 'provider': 'openai_api', 'model': 'gpt-6.1-sol', 'effort': 'low',
                  'service_tier': 'ultrafast', 'max_output_tokens': 512}
    mode = ('realtime_api' if paid else 'real_time_subscription') if a.command == 'eval' else 'subscription_with_simulated_profile'
    out, result = experiment.execute(a, recipe, mode, asterix)
    print(json.dumps({'output': str(out), 'result': result}, indent=2))
