"""Report candidate-set agreement without claiming safety or survival accuracy."""
import argparse
import collections
import json
from pathlib import Path


def summarize(records, annotations):
    labels = {a['case_id']: a['human_candidate_safe_actions'] for a in annotations
              if a['case_id'].startswith('C') and a['human_candidate_safe_actions'] is not None}
    grouped = collections.defaultdict(list)
    seen = set()
    for record in records:
        key = (record['variant'], record['case_id'], record['repeat'])
        if key in seen:
            raise ValueError('Duplicate result')
        seen.add(key)
        if record['case_id'] not in labels:
            raise ValueError('Unlabeled or auxiliary case in scored results')
        grouped[record['variant']].append(record)
    output = {}
    for variant, rows in sorted(grouped.items()):
        by_case = {}
        for cid in sorted({r['case_id'] for r in rows}):
            calls = [r for r in rows if r['case_id'] == cid]
            hits = sum(type(r['action']) is int and r['action'] in labels[cid] for r in calls)
            by_case[cid] = {'calls': len(calls), 'agrees': hits,
                            'actions': dict(collections.Counter(str(r['action']) for r in calls))}
        hits = sum(c['agrees'] for c in by_case.values())
        output[variant] = {'calls': len(rows), 'agrees': hits,
                           'agreement_fraction': hits/len(rows),
                           'valid_actions': sum(type(r['action']) is int and 0 <= r['action'] <= 8 for r in rows),
                           'per_case': by_case}
    return {'metric': 'human candidate-set agreement; not survival accuracy', 'variants': output}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--annotations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = summarize([json.loads(line) for line in args.results.read_text().splitlines()],
                       json.loads(args.annotations.read_text())['annotations'])
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({v:{k:x for k,x in r.items() if k != 'per_case'} for v,r in report['variants'].items()}))
