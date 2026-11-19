#!/usr/bin/env python3
"""Claim register: every synthesized conclusion with a strength label and
evidence ids. quote_check is computed later by verify.py. Stdlib only."""
import argparse
import json
import os
import time


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save(path, obj):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('add')
    a.add_argument('--claims', required=True)
    a.add_argument('--claim', required=True, help='结论句（完整句子）')
    a.add_argument('--strength', required=True,
                   choices=['fact', 'inference', 'unknown'])
    a.add_argument('--evidence', default='',
                   help='逗号分隔的证据号，如 EV-0001,EV-0002')
    a.add_argument('--section', default='结论',
                   help='所属段落：结论/冲突证据/研究空白/无法确定')
    l = sub.add_parser('list')
    l.add_argument('--claims', required=True)
    args = ap.parse_args()

    if args.cmd == 'list':
        reg = load(args.claims)
        for c in reg['claims']:
            print(json.dumps(c, ensure_ascii=False))
        return

    reg = load(args.claims)
    ev = [x.strip() for x in args.evidence.split(',') if x.strip()]
    cid = 'CL-%04d' % reg['next_id']
    reg['next_id'] += 1
    reg['claims'].append({
        'claim_id': cid, 'text': args.claim, 'strength': args.strength,
        'evidence_ids': ev, 'section': args.section,
        'quote_check': 'pending',  # set by verify.py
        'entered_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    save(args.claims, reg)
    print(json.dumps({'ok': True, 'claim_id': cid,
                      'note': 'quote_check 由 verify.py 计算'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
