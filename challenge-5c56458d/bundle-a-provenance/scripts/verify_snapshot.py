#!/usr/bin/env python3
"""Verify a snapshot fingerprint against reference cards of known datasets.

The script answers three questions before any analysis begins:
  1. Which known dataset (if any) does this table actually look like?
  2. Does the snapshot match that reference within tolerance, or has it
     drifted (rows added/lost, values rescaled, classes relabelled)?
  3. For datasets with known variants (e.g. UCI iris.data vs
     bezdekIris.data), which variant is this?

Column matching is name-normalized first (case/punctuation-insensitive,
alias table applied) and positional as fallback, so renamed-but-identical
snapshots still verify. Every verdict carries the evidence list; nothing is
silently "fixed". Standard library only.

Usage:
  python verify_snapshot.py --fingerprint /app/work/fingerprint.json \
      --cards <skill>/references/reference_cards.json \
      --out /app/work/verdict.json --md /app/work/verdict.md
"""
import argparse
import json
import math
import os
import re
import sys

REL_TOL = 0.01          # relative tolerance for mean/std comparisons
MIN_SCORE = 3.0         # minimum evidence score to claim a card match


def norm(name):
    return re.sub(r'[^a-z0-9]+', '_', str(name).lower()).strip('_')


def rel_diff(a, b):
    if a == b:
        return 0.0
    denom = max(abs(a), abs(b), 1e-12)
    return abs(a - b) / denom


def numeric_cols(table):
    return [c for c in table['columns'] if 'numeric' in c]


def value_multiset(table):
    """Best-effort class-count multiset from a low-cardinality column."""
    best = None
    for c in table['columns']:
        tv = c.get('top_values')
        if not tv or c['distinct_count'] > 12 or c['distinct_count'] < 2:
            continue
        counts = sorted(v['count'] for v in tv)
        if best is None or len(counts) > len(best[1]):
            best = (c['name'], counts, {v['value']: v['count'] for v in tv})
    return best


def score_card(table, card):
    """Score how well a fingerprinted table matches one reference card."""
    score, why = 0.0, []
    exp_rows = card['row_count']
    got_rows = table['row_count']
    if got_rows == exp_rows:
        score += 2.0
        why.append('row_count exact (%d)' % got_rows)
    elif abs(got_rows - exp_rows) / exp_rows <= 0.05:
        score += 0.5
        why.append('row_count close (%d vs %d)' % (got_rows, exp_rows))
    feats = card.get('feature_columns', [])
    ncols = numeric_cols(table)
    if len(ncols) == len(feats) or len(ncols) == len(feats) + 1:
        score += 1.0
        why.append('numeric column count %d consistent' % len(ncols))
    # name-normalized alias matching
    aliases = {norm(f): f for f in feats}
    for f in feats:
        for a in card.get('aliases', {}).get(f, []):
            aliases.setdefault(norm(a), f)
    byname = {norm(c['name']): c for c in ncols}
    matched = 0
    for c in ncols:
        key = norm(c['name'])
        f = aliases.get(key)
        if f and f in card['column_stats']:
            exp = card['column_stats'][f]
            if rel_diff(c['numeric']['mean'], exp['mean']) <= REL_TOL * 4:
                matched += 1
    if matched:
        score += min(matched, 4) * 0.5
        why.append('%d columns name+stat matched' % matched)
    # positional fallback: compare i-th numeric column with i-th feature
    if matched == 0 and len(ncols) >= len(feats) and feats:
        pos = 0
        for i, f in enumerate(feats):
            exp = card['column_stats'].get(f)
            if exp and rel_diff(ncols[i]['numeric']['mean'], exp['mean']) <= REL_TOL * 4:
                pos += 1
        if pos:
            score += min(pos, 4) * 0.5
            why.append('%d columns positionally stat-matched' % pos)
    cc = card.get('class_counts')
    if cc:
        vm = value_multiset(table)
        if vm and sorted(cc.values()) == vm[1]:
            score += 1.0
            why.append('class-count multiset matches (%s)' % vm[0])
    return score, why


def compare_columns(table, card):
    """Detailed per-column drift list against the matched card."""
    feats = card.get('feature_columns', [])
    aliases = {norm(f): f for f in feats}
    for f in feats:
        for a in card.get('aliases', {}).get(f, []):
            aliases.setdefault(norm(a), f)
    ncols = numeric_cols(table)
    byname = {}
    for c in ncols:
        f = aliases.get(norm(c['name']))
        if f and f not in byname:
            byname[f] = c
    diffs, checks = [], 0
    for i, f in enumerate(feats):
        exp = card['column_stats'].get(f)
        if not exp:
            continue
        got = byname.get(f)
        how = 'name'
        if got is None and i < len(ncols) and len(ncols) >= len(feats):
            got, how = ncols[i], 'position'
        if got is None:
            diffs.append({'column': f, 'issue': 'no candidate column in snapshot'})
            continue
        checks += 1
        for stat in ('min', 'max', 'mean', 'std'):
            d = rel_diff(got['numeric'][stat], exp[stat])
            if d > REL_TOL:
                diffs.append({'column': f, 'snapshot_column': got['name'],
                              'matched_by': how, 'stat': stat,
                              'expected': exp[stat], 'observed': got['numeric'][stat],
                              'rel_diff': round(d, 5)})
    return checks, diffs


def verdict_for_table(tname, table, cards):
    scored = []
    for cid, card in cards.items():
        s, why = score_card(table, card)
        scored.append((s, cid, why))
    scored.sort(reverse=True)
    rec = {'table': tname, 'row_count': table['row_count'],
           'candidates': [{'card': c, 'score': s, 'evidence': w}
                          for s, c, w in scored[:3]]}
    if not scored or scored[0][0] < MIN_SCORE:
        rec['verdict'] = 'NO_CARD'
        rec['meaning'] = ('no reference card explains this table; the fingerprint '
                          'itself is the only provenance record — report it and '
                          'proceed without external ground truth')
        return rec
    score, cid, why = scored[0]
    card = cards[cid]
    rec['matched_card'] = cid
    rec['card_source'] = card.get('source', '')
    checks, diffs = compare_columns(table, card)
    rec['columns_checked'] = checks
    rec['drift'] = diffs
    row_ok = table['row_count'] == card['row_count']
    cc = card.get('class_counts')
    class_ok, class_note = None, ''
    if cc:
        vm = value_multiset(table)
        if vm:
            class_ok = sorted(cc.values()) == vm[1]
            class_note = 'column=%s observed=%s expected=%s' % (
                vm[0], vm[2], cc)
    rec['class_check'] = {'ok': class_ok, 'note': class_note} if cc else None
    if row_ok and not diffs and class_ok is not False:
        rec['verdict'] = 'VERIFIED'
    else:
        rec['verdict'] = 'DRIFT'
    # variant discrimination: list other cards of the same family
    family = cid.split('-')[0]
    rec['same_family_cards'] = [c for c in cards
                                if c.split('-')[0] == family and c != cid]
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--fingerprint', required=True)
    ap.add_argument('--cards', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--md', help='optional Markdown verdict report')
    args = ap.parse_args()
    fp = json.load(open(args.fingerprint, encoding='utf-8'))
    cards = json.load(open(args.cards, encoding='utf-8'))['cards']
    verdicts = []
    for db in fp['databases']:
        if 'error' in db:
            verdicts.append({'database': db['path'], 'verdict': 'UNREADABLE',
                             'error': db['error']})
            continue
        for tname, table in db.get('tables', {}).items():
            v = verdict_for_table(tname, table, cards)
            v['database'] = db['path']
            v['database_sha256'] = db['sha256']
            verdicts.append(v)
    overall = 'VERIFIED' if verdicts and all(
        v['verdict'] == 'VERIFIED' for v in verdicts) else (
        'DRIFT' if any(v.get('verdict') == 'DRIFT' for v in verdicts) else
        'NO_CARD' if verdicts else 'EMPTY_INPUT')
    out = {'tool': 'verify_snapshot.py', 'overall': overall, 'tables': verdicts,
           'tolerance': {'rel_stat': REL_TOL, 'min_score': MIN_SCORE},
           'note': ('VERIFIED = snapshot matches a reference card within '
                    'tolerance; DRIFT = matched card but differences exist '
                    '(see drift list, report them, do not repair silently); '
                    'NO_CARD = unknown dataset, fingerprint is the provenance '
                    'record of last resort.')}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(out, open(args.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    if args.md:
        lines = ['# Snapshot authenticity verdict', '',
                 'Overall: **%s**' % overall, '']
        for v in verdicts:
            lines.append('## %s :: %s' % (os.path.basename(v.get('database', '?')),
                                          v.get('table', '?')))
            lines.append('- verdict: %s; rows: %s; card: %s (%s)' % (
                v.get('verdict'), v.get('row_count'),
                v.get('matched_card', '—'), v.get('card_source', '—')))
            for d in v.get('drift', [])[:20]:
                lines.append('- DRIFT %s' % json.dumps(d, ensure_ascii=False))
            if v.get('same_family_cards'):
                lines.append('- same-family variants considered: %s'
                             % ', '.join(v['same_family_cards']))
            lines.append('')
        open(args.md, 'w', encoding='utf-8').write('\n'.join(lines))
    print(json.dumps({'overall': overall,
                      'tables': [{'table': v.get('table'), 'verdict': v.get('verdict'),
                                  'card': v.get('matched_card')} for v in verdicts]},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
