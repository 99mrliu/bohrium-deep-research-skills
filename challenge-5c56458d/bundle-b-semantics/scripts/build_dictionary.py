#!/usr/bin/env python3
"""Build a data dictionary for a snapshot from field profiles + semantics pack.

Output is a *draft grounded in evidence*: every entry states whether its
meaning comes from the semantics pack (name/alias match, confidence levels)
or remains unresolved. Unresolved fields are NOT guessed — they are listed
in the ambiguity queue for the task-provided dictionary or human ruling.
Standard library only.

Usage:
  python build_dictionary.py --profile /app/work/field_profile.json \
      --pack <skill>/references/semantics_pack.json \
      --out /app/work/data_dictionary.json --md /app/work/data_dictionary.md
"""
import argparse
import json
import os
import re
import sys


def norm(name):
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')


def pack_index(pack):
    """normalized name/alias -> (dataset, canonical field, entry)"""
    idx = {}
    for ds, body in pack['datasets'].items():
        for canon, entry in body['fields'].items():
            for alias in [canon] + entry.get('aliases', []):
                idx.setdefault(norm(alias), []).append((ds, canon, entry))
    return idx


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--profile', required=True)
    ap.add_argument('--pack', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--md', required=True)
    args = ap.parse_args()
    prof = json.load(open(args.profile, encoding='utf-8'))
    pack = json.load(open(args.pack, encoding='utf-8'))
    idx = pack_index(pack)
    dictionary = {'database': prof['database'], 'source': pack['meta']['provenance'],
                  'tables': {}, 'ambiguity_queue': []}
    for tname, table in prof['tables'].items():
        entries = []
        for col in table['columns']:
            key = norm(col['name'])
            hits = idx.get(key, [])
            e = {'column': col['name'], 'role': col['role'],
                 'observed': {'null_count': col['null_count'],
                              'distinct': col['evidence']['distinct'],
                              'range': col.get('range'),
                              'levels': col.get('levels')}}
            if len(hits) == 1:
                ds, canon, entry = hits[0]
                e.update(confidence='pack_match', dataset=ds,
                         canonical=canon, meaning=entry.get('meaning'),
                         unit=entry.get('unit'), caliber=entry.get('caliber'),
                         coding=entry.get('coding'))
            elif len(hits) > 1:
                e.update(confidence='ambiguous_name',
                         candidates=[{'dataset': ds, 'field': c}
                                     for ds, c, _ in hits])
                dictionary['ambiguity_queue'].append(
                    {'table': tname, 'column': col['name'],
                     'issue': 'name matches %d pack fields' % len(hits),
                     'candidates': e['candidates']})
            else:
                e.update(confidence='unresolved',
                         meaning=None, unit=None, caliber=None)
                if col['role'] not in ('identifier', 'constant', 'empty'):
                    dictionary['ambiguity_queue'].append(
                        {'table': tname, 'column': col['name'],
                         'issue': 'no pack semantics; needs task dictionary '
                                  'or explicit statement of interpretation'})
            if col['role'] == 'numeric_coded_category':
                e['warning'] = ('numeric-coded category: do not aggregate as a '
                                'measure; see confusable_fields.md')
            entries.append(e)
        dictionary['tables'][tname] = {'row_count': table['row_count'],
                                       'fields': entries}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(dictionary, open(args.out, 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    lines = ['# Data dictionary (draft, evidence-grounded)', '',
             'Database: `%s`' % prof['database'], '']
    for tname, tbody in dictionary['tables'].items():
        lines.append('## Table `%s` (%d rows)' % (tname, tbody['row_count']))
        lines.append('| column | role | meaning | unit | caliber | confidence |')
        lines.append('|-|-|-|-|-|-|')
        for e in tbody['fields']:
            lines.append('| %s | %s | %s | %s | %s | %s |' % (
                e['column'], e['role'], e.get('meaning') or '—',
                e.get('unit') or '—', (e.get('caliber') or '—'), e['confidence']))
        lines.append('')
    if dictionary['ambiguity_queue']:
        lines.append('## Ambiguity queue (must be resolved or declared)')
        for a in dictionary['ambiguity_queue']:
            lines.append('- `%s.%s`: %s' % (a['table'], a['column'], a['issue']))
        lines.append('')
    open(args.md, 'w', encoding='utf-8').write('\n'.join(lines))
    print(json.dumps({'out': args.out, 'md': args.md,
                      'fields': sum(len(t['fields']) for t in
                                    dictionary['tables'].values()),
                      'ambiguities': len(dictionary['ambiguity_queue'])},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
