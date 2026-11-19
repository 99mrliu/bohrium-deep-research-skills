#!/usr/bin/env python3
"""Append-only run journal with a SHA-256 hash chain.

Every tool call during the research run is recorded as one JSONL entry:
{seq, ts, prev, hash, tool, args, results_count, results_digest, sq, note, status}
- hash = sha256(prev + canonical(entry-without-hash))
- verify  : recompute the chain; any edit/insert/delete is detected.
- replay  : print an ordered replay script a third party can follow.
Stdlib only.
"""
import argparse
import hashlib
import json
import time


def _canon(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def _entry_hash(prev, body):
    return hashlib.sha256((prev + _canon(body)).encode('utf-8')).hexdigest()


def init(path, case_id):
    body = {'seq': 0, 'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                          time.gmtime()),
            'tool': 'genesis', 'case_id': case_id, 'note': 'journal opened',
            'status': 'ok'}
    entry = dict(body)
    entry['prev'] = '0' * 64
    entry['hash'] = _entry_hash(entry['prev'], body)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def append(path, tool, args, results_count=None, results_digest=None,
           sq=None, note='', status='ok'):
    with open(path, encoding='utf-8') as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    if not lines:
        raise SystemExit('journal not initialized: %s' % path)
    last = json.loads(lines[-1])
    body = {'seq': last['seq'] + 1,
            'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'tool': tool, 'args': args,
            'results_count': results_count, 'results_digest': results_digest,
            'sq': sq, 'note': note, 'status': status}
    entry = dict(body)
    entry['prev'] = last['hash']
    entry['hash'] = _entry_hash(entry['prev'], body)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    print(json.dumps({'appended': entry['seq'], 'hash': entry['hash'][:16],
                      'status': status}, ensure_ascii=False))


def verify(path):
    with open(path, encoding='utf-8') as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    errors, prev = [], '0' * 64
    for i, line in enumerate(lines):
        entry = json.loads(line)
        body = {k: v for k, v in entry.items() if k not in ('prev', 'hash')}
        if entry.get('prev') != prev:
            errors.append('line %d: prev mismatch' % (i + 1))
        if _entry_hash(prev, body) != entry.get('hash'):
            errors.append('line %d: hash mismatch (content altered)' % (i + 1))
        prev = entry.get('hash', '')
    summary = {'ok': not errors, 'entries': len(lines),
               'chain_head': prev[:16], 'errors': errors[:10]}
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not errors else 1


def replay(path):
    with open(path, encoding='utf-8') as f:
        for line in f:
            e = json.loads(line)
            args = _canon(e.get('args')) if e.get('args') is not None else ''
            if len(args) > 200:
                args = args[:200] + '…'
            print('#%04d [%s] %s sq=%s status=%s\n  args: %s\n  expect results_count=%s digest=%s\n  note: %s'
                  % (e['seq'], e['ts'], e['tool'], e.get('sq'),
                     e.get('status'), args, e.get('results_count'),
                     e.get('results_digest'), e.get('note')))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('append')
    p.add_argument('--journal', required=True)
    p.add_argument('--tool', required=True)
    p.add_argument('--args', required=True, help='JSON string')
    p.add_argument('--results-count', type=int)
    p.add_argument('--results-digest')
    p.add_argument('--sq')
    p.add_argument('--note', default='')
    p.add_argument('--status', default='ok',
                   choices=['ok', 'retry', 'failed', 'degraded'])
    v = sub.add_parser('verify')
    v.add_argument('--journal', required=True)
    r = sub.add_parser('replay')
    r.add_argument('--journal', required=True)
    i = sub.add_parser('init')
    i.add_argument('--journal', required=True)
    i.add_argument('--case-id', required=True)
    a = ap.parse_args()
    if a.cmd == 'init':
        init(a.journal, a.case_id)
        print(json.dumps({'initialized': a.journal}, ensure_ascii=False))
    elif a.cmd == 'append':
        append(a.journal, a.tool, json.loads(a.args), a.results_count,
               a.results_digest, a.sq, a.note, a.status)
    elif a.cmd == 'verify':
        raise SystemExit(verify(a.journal))
    elif a.cmd == 'replay':
        replay(a.journal)


if __name__ == '__main__':
    main()
