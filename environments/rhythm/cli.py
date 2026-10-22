"""Command entrypoint for the selected Rhythm experiments."""
import json

from runtime import experiment
from runtime.run_support import ROOT

def main(argv=None):
    p = experiment.parser("rhythm", profiling=True)
    a = p.parse_args(argv)
    a.game = "rhythm"
    if a.command in ('eval', 'profile'):
        experiment.validate_budget(p, a)
    from runtime import rhythm
    if a.command == 'profile':
        print(json.dumps(rhythm.profile(ROOT, a), indent=2))
        return
    recipe = json.loads((a.recipe or ROOT/'recipes/rhythm.json').read_text())
    action = rhythm.evaluate if a.command == 'eval' else rhythm.simulate
    mode = 'realtime_api' if a.command == 'eval' else 'subscription_with_simulated_profile'
    out, result = experiment.execute(a, recipe, mode, lambda recipe, out, args: action(ROOT, recipe, out, args))
    if a.command == 'eval':
        result = {k: v for k, v in result.items() if k in ('complete', 'passed', 'native_clock_drift_s', 'result', 'requests', 'errors')}
    print(json.dumps({'output': str(out), 'result': result}, indent=2))
