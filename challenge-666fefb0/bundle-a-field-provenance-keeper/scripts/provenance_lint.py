#!/usr/bin/env python3
"""provenance_lint.py — mechanical anchor verification of metadata claims.

For every non-unknown metadata value in decisions.json:
  1. the value (whitespace-normalized) must anchor in the file's evidence pool
     (extracted text + filename + matching sidecar rows), full substring OR all
     significant tokens present;
  2. if an evidence snippet is supplied, it must itself anchor in the pool.
Failures downgrade the field to `unknown` and are recorded in conflicts.json —
the model can only overturn a downgrade by supplying stronger verbatim evidence
and re-running the lint, never by editing lint output.
"""
import json
import os
import re
import sys

from inventory import read_json, write_json

FIELDS = ('title', 'authors', 'year', 'venue', 'doi')
TOKEN_RE = re.compile(r'[A-Za-z0-9]{3,}')


def norm(s):
    return re.sub(r'\s+', ' ', str(s or '')).strip().lower()


def evidence_pool(work_dir, fid, rel, sidecars):
    parts = [norm(rel)]
    ext_path = os.path.join(work_dir, 'extracted', f'{fid}.txt')
    if os.path.isfile(ext_path):
        with open(ext_path, encoding='utf-8', errors='replace') as f:
            parts.append(norm(f.read()))
    for sc in sidecars:
        excerpt = sc.get('content_excerpt') or ''
        if rel.split('/')[-1].split('.')[0].lower() in norm(excerpt) or sc.get('fid') == fid:
            parts.append(norm(excerpt))
        for row in (sc.get('csv_rows') or []):
            row_text = ' '.join(str(v) for v in row.values())
            if fid.lower() in row_text.lower() or norm(os.path.splitext(os.path.basename(rel))[0])[:12] in norm(row_text):
                parts.append(norm(row_text))
    return ' '.join(parts)


def anchored(value, pool):
    v = norm(value)
    if not v or v == 'unknown':
        return True, 'trivial'
    if v in pool:
        return True, 'substring'
    tokens = [t.lower() for t in TOKEN_RE.findall(v)]
    if tokens and all(t in pool for t in tokens):
        return True, 'tokens'
    return False, 'no_anchor'


def run_lint(work_dir):
    decisions_path = os.path.join(work_dir, 'decisions.json')
    decisions = read_json(decisions_path)
    sidecars_path = os.path.join(work_dir, 'sidecars.json')
    sidecars = read_json(sidecars_path) if os.path.isfile(sidecars_path) else []
    files = {}
    with open(os.path.join(work_dir, 'files.jsonl'), encoding='utf-8') as f:
        for line in f:
            rec = json.loads(line)
            files[rec['fid']] = rec

    report = {'checked': 0, 'passed': 0, 'downgraded': [], 'evidence_issues': []}
    conflicts = []
    pools = {}

    for a in decisions.get('assignments', []):
        fid = a.get('fid')
        if fid not in files:
            conflicts.append({'fid': fid, 'field': None, 'issue': 'unknown fid in decisions.json'})
            continue
        if fid not in pools:
            pools[fid] = evidence_pool(work_dir, fid, files[fid]['rel'], sidecars)
        pool = pools[fid]
        meta = a.setdefault('metadata', {})
        for field_name in FIELDS:
            entry = meta.get(field_name)
            if not isinstance(entry, dict):
                entry = {'value': str(entry)} if entry else {'value': 'unknown'}
                meta[field_name] = entry
            value = entry.get('value')
            if value in (None, '', 'unknown'):
                entry['value'] = 'unknown'
                entry.setdefault('lint', 'skipped_unknown')
                continue
            report['checked'] += 1
            ok, how = anchored(value, pool)
            if ok:
                report['passed'] += 1
                entry['lint'] = f'anchored:{how}'
            else:
                report['downgraded'].append({'fid': fid, 'field': field_name,
                                             'rejected_value': value, 'reason': 'value not anchored in evidence pool'})
                conflicts.append({'fid': fid, 'field': field_name, 'issue': 'lint_downgrade',
                                  'rejected_value': value,
                                  'note': 'value could not be verified against extracted text/filename/sidecars; downgraded to unknown'})
                entry.update({'value': 'unknown', 'lint': 'downgraded:no_anchor',
                              'rejected_value': value})
            ev = entry.get('evidence')
            if ev:
                ok_ev, _ = anchored(ev, pool)
                if not ok_ev:
                    report['evidence_issues'].append({'fid': fid, 'field': field_name,
                                                      'issue': 'evidence snippet not anchored'})
                    entry['lint'] = str(entry.get('lint', '')) + ';evidence_unanchored'

    write_json(os.path.join(work_dir, 'decisions.linted.json'), decisions)
    write_json(os.path.join(work_dir, 'lint_report.json'), report)
    write_json(os.path.join(work_dir, 'conflicts.json'), conflicts)
    return report, conflicts


if __name__ == '__main__':
    rep, conf = run_lint(sys.argv[1])
    print(json.dumps({'checked': rep['checked'], 'passed': rep['passed'],
                      'downgraded': len(rep['downgraded'])}, ensure_ascii=False))
