"""Strictly serial profiling against recorded actual frontend PNG fixtures.

Run with python -m research.profile_api --fixtures fixtures.json ...
The API key is read via getpass or inherited OPENAI_API_KEY, never written.
"""
import argparse
import fcntl
import getpass
import json
import math
import os
from pathlib import Path
import statistics
import time

from .api_client import ApiClient


def legal_action(answer):
    obj = json.loads(answer)
    if not isinstance(obj, list) or not obj:
        raise ValueError("Expected nonempty action list")
    chunks = obj if isinstance(obj[0], list) else [obj]
    if not 1 <= len(chunks) <= 4:
        raise ValueError("Expected 1-4 action chunks")
    for action in chunks:
        if not isinstance(action, list) or len(action) != 5 or any(type(x) is not int for x in action):
            raise ValueError("Expected [move,shoot,focus,bomb,duration]")
        move, shoot, focus, bomb, duration = action
        if move not in range(9) or any(x not in (0, 1) for x in (shoot, focus, bomb)) or duration not in (6, 12, 24, 48):
            raise ValueError("Action outside protocol bounds")
    return True


def general_action(answer,max_chunks=4):
    from .scheduler import parse_plan
    plan=parse_plan(answer)
    if len(plan)>max_chunks or any(a.duration>48 for a in plan):raise ValueError('Frozen plan bounds exceeded')
    return True


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    position = (len(values)-1) * q
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high]-values[low]) * (position-low)


def summarize(samples):
    out = {}
    for name in sorted({s["group"] for s in samples}):
        group = [s for s in samples if s["group"] == name]
        stats = {"n": len(group), "invalid": sum(not s["meta"]["valid"] for s in group), "usd": sum(float(s["meta"]["usd"]) for s in group)}
        for metric in ("ttft_s", "legal_action_s", "total_s", "prepare_s"):
            values = [s["meta"][metric] for s in group if s["meta"][metric] is not None]
            stats[metric] = {"n": len(values), "min": min(values) if values else None, **{label: percentile(values, q) for label, q in (("p10", .1), ("p50", .5), ("p90", .9), ("p95", .95))}}
        out[name] = stats
    return {"latency_metric": "total_s", "samples_s": [s["meta"]["total_s"] for s in samples if s["meta"]["valid"]], "groups": out}


def profile_schema(candidate,structured,max_chunks=1):
    from .wire_schema import decision_schema,FORECAST_CANDIDATES
    if not structured:return None,False
    return decision_schema(candidate,max_chunks,48),candidate in FORECAST_CANDIDATES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", required=True)
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--stage", choices=("profile", "reprofile"), default="profile")
    parser.add_argument("--max-output-tokens", type=int, default=128)
    parser.add_argument("--general-plan",action="store_true")
    parser.add_argument("--structured",action="store_true",help="Use strict grounded-plan JSON schema (pair with --general-plan)")
    parser.add_argument("--candidate",help="Candidate-specific structured schema; otherwise infer from fixture manifest")
    parser.add_argument("--max-chunks",type=int,choices=range(1,5),default=1)
    parser.add_argument("--detail", choices=("low", "high", "auto"), default="high")
    args = parser.parse_args()
    if args.samples <= 0:
        parser.error("--samples must be positive")
    if args.structured and not args.general_plan:
        parser.error("--structured requires --general-plan")
    fixture_path = Path(args.fixtures)
    manifest = json.loads(fixture_path.read_text())
    declared = manifest.get('candidate') if isinstance(manifest,dict) else None
    if args.candidate and declared and args.candidate != declared:
        parser.error('Candidate differs from frozen fixture manifest')
    candidate = args.candidate or declared or ''
    if args.candidate and not args.structured:
        parser.error('--candidate requires --structured')
    if args.candidate:
        from .policies import STRATEGIES
        if args.candidate not in STRATEGIES:parser.error('Unknown candidate')
    output_schema,preserve_order = profile_schema(candidate,args.structured,args.max_chunks)
    from .wire_schema import schema_hash
    config=manifest.get('model_configuration',{}) if isinstance(manifest,dict) else {}
    expected={'schema_sha256':schema_hash(output_schema),'max_chunks':args.max_chunks,'max_output_tokens':args.max_output_tokens,'detail':args.detail,'preserve_schema_order':preserve_order}
    for key,value in expected.items():
        if key in config and config[key]!=value:
            parser.error('Profiling configuration differs from frozen fixture: '+key)
    if 'schema_order_sha256' in config:
        import hashlib
        actual=hashlib.sha256(json.dumps(output_schema,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        if actual!=config['schema_order_sha256']:parser.error('Schema property order differs from frozen fixture')
    fixtures = manifest['fixtures'] if isinstance(manifest,dict) else manifest
    # Lock shared across profiler processes using the same global ledger.
    # Nonblocking ensures accidental double startup fails before any paid call.
    Path(args.ledger).parent.mkdir(parents=True, exist_ok=True)
    with open(args.ledger + ".profile.lock", "a") as serial:
        fcntl.flock(serial, fcntl.LOCK_EX | fcntl.LOCK_NB)
        key = os.environ.pop("OPENAI_API_KEY", None) or getpass.getpass("API key (not saved): ")
        client = ApiClient(key, args.ledger, args.stage, args.max_output_tokens, detail=args.detail, output_schema=output_schema,preserve_schema_order=preserve_order)
        samples = []
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x") as raw:
            for fixture in fixtures:
                images = [(fixture_path.parent / p).read_bytes() for p in fixture["images"]]
                for index in range(args.samples):
                    validator=(lambda answer:general_action(answer,args.max_chunks)) if args.general_plan else legal_action
                    result = client.decide(fixture["prompt"], images, validator)
                    record = {**result, "group": fixture["name"], "index": index, "connection": "cold" if not samples else "warm", "wall_time": time.time()}
                    raw.write(json.dumps(record) + "\n")
                    raw.flush()
                    os.fsync(raw.fileno())
                    samples.append(record)
                    Path(str(output) + ".summary.json").write_text(json.dumps(summarize(samples), indent=2))


if __name__ == "__main__":
    main()
