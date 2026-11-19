#!/usr/bin/env python3
"""Conflict detection over the study matrix.

A conflict pair = two rows sharing (topic, outcome) with mutually exclusive
directions (positive vs negative, or positive/negative vs none when both
claim an effective test). Each pair must carry an adjudication basis
(design tier / sample size / directional consistency); finalize refuses
success while any pair lacks it. Stdlib only.
"""
import argparse
import json
import os

OPPOSE = {('positive', 'negative'), ('positive', 'none'),
          ('negative', 'none')}


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def detect(rows):
    pairs = []
    by_key = {}
    for i, r in enumerate(rows, 1):
        by_key.setdefault((r['topic'], r['outcome']), []).append((i, r))
    for (topic, outcome), items in sorted(by_key.items()):
        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                (ia, ra), (ib, rb) = items[a], items[b]
                key = (ra['direction'], rb['direction'])
                if key in OPPOSE or (key[1], key[0]) in OPPOSE:
                    pairs.append({'pair_id': 'CF-%03d' % (len(pairs) + 1),
                                  'topic': topic, 'outcome': outcome,
                                  'rows': [ia, ib],
                                  'side_a': {'row': ia, **ra},
                                  'side_b': {'row': ib, **rb},
                                  'adjudication': None,
                                  'adjudication_basis': None})
    return pairs, by_key


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--matrix', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    m = load(args.matrix)
    pairs, by_key = detect(m['rows'])
    reg = {'case_id': m['case_id'], 'conflict_pairs': pairs,
           'rule': '同 (topic,outcome) 内 direction 互斥的研究对；'
                   'adjudication 必填：写明依据（设计层级/样本量/一致性）'
                   '与"更支持哪方/仍无法裁定+缺什么证据"，禁止空话'}
    save(os.path.join(args.out, 'conflict_register.json'), reg)
    print(json.dumps({'ok': True, 'conflict_pairs': len(pairs),
                      'topics': len(by_key)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
