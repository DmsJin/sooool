"""Extract joint public-transport timings from a completed native run.

No chart, game state, note coordinates or model action times are read.
The resulting data drives trusted simulation conditions, never actor prompts.
"""
import argparse
import json
import math
from pathlib import Path


def extract(source, output):
    source, output = Path(source), Path(output)
    if output.exists():
        raise ValueError('Refusing to overwrite joint profile')
    rows, excluded = [], []
    for line in source.read_text().splitlines():
        row = json.loads(line)
        metadata=row.get('metadata',{})
        delivery=row.get('action_delivery',{})
        if 'receipt' not in row or not (metadata or delivery):
            excluded.append({'version': row['version'], 'reason': 'No delivered decision timing'})
            continue
        now = row['observation']['external_now_ms']
        frame = row['frame_metadata'][-1]['capture_end_ms']
        received = row['receipt']['clock_ms']
        api = delivery.get('action_ready_s',metadata.get('latency_s'))
        age, overhead = (now - frame) / 1000, (received - now) / 1000 - api
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in (age, api, overhead)) or api <= 0 or age < 0 or overhead < 0:
            raise ValueError('Invalid joint timings in request ' + str(row['version']))
        # The action may be applied while the same HTTP request still drains.
        # Preserve that correlated capacity cost instead of freeing its actor
        # at action delivery. A failed tail has unknown occupancy: refuse to
        # silently turn it into a short completed request distribution.
        if delivery and not metadata:
            raise ValueError('Delivered action has unknown request occupancy; preserve failure separately')
        occupancy=api+overhead
        if delivery:
            occupancy=max(occupancy,metadata['total_provider_s']+overhead-
                          metadata['pre_http_s']-metadata['action_callback_s'])
        rows.append({'status': 'completed', 'request_version': row['version'],
                     'api_rtt_s': api, 'frame_age_s': age,
                     'transport_overhead_s': overhead,'request_occupancy_s':occupancy,
                     'completion_rtt_s':metadata['latency_s']})
    rows.sort(key=lambda r: r['request_version'])
    if not rows:
        raise ValueError('No completed native timing samples')
    profile = {'schema': 1, 'kind': 'joint_native_transport_conditions',
               'source': str(source.resolve()),
               'rows': rows, 'excluded_without_completed_metadata': excluded,
               'selection': 'Every completed response with public frame/snapshot/apply clocks; action readiness and request occupancy distinct; tails retained',
               'actor_exposure': 'None; these are trusted simulation conditions only',
               'limitations': ['Within-row correlation is preserved; random resampling does not preserve temporal correlation.',
                               'Request occupancy is estimated from public receipt/provider clocks, including stream drain and settlement.',
                               'Conditions reflect the recorded source configuration; later sensor, host or load changes may differ.']}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(profile, indent=2))
    print(json.dumps({'samples': len(rows), 'excluded': len(excluded), 'output': str(output)}))
    return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    extract(args.source, args.output)
