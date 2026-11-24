#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_alignment.py — Verify a bilingual master file against the segment spine.

Bilingual paired-block format (spec in references/method.md):

    ⟦S0001⟧ heading
    > SRC
    # Original Title

    > TGT
    # 中文标题

    ⟦S0002⟧ paragraph
    > SRC
    ...

    > TGT
    ...

Parser: tolerant of blank lines, strict about IDs (⟦Sdddd⟧, each exactly
once, source order). `> NOTE` blocks are translator notes and are ignored
by the checker (they are not TGT).

Usage:
    python3 check_alignment.py BILINGUAL SEGMENTS [--json REPORT.json]

Checks per segment (in source order):
  * present exactly once in bilingual.md, IDs in source order
    (no reorder / merge / drop)
  * both a SRC block and a TGT block exist and are non-empty
  * structural markers match between SRC and TGT:
      - figure/table numbers (Figure 1, Fig. 2, Table 3, 图 1, 表 2)
      - equation bodies unchanged (whitespace-normalized, equation segments)
      - footnote markers [^id]
      - citation markers [12], [3,4], [5-7]

Verdicts: ok | missing_tgt | missing_src | marker_mismatch | order_violation
Exit codes: 0 pass, 1 alignment failures, 2 usage/IO error.
Stdlib only. No network.
"""
import argparse
import json
import re
import sys
from collections import Counter

SEG_HEAD_RE = re.compile(r'^⟦(S\d{4})⟧\s+(\w+)\s*$')
BID_RE = re.compile(r'^⟦(S\d{4})⟧\s*(\w*)\s*$')
MARK_RE = re.compile(r'^>\s*(SRC|TGT|NOTE)\s*$')

CIT_RE = re.compile(r'\[\d+(?:\s*[-–,]\s*\d+)*\]')
FN_RE = re.compile(r'\[\^[^\]]+\]')
FT_SRC_RE = re.compile(r'(?i)\b(?:figure|fig\.?|table)\s*\.?\s*(\d+(?:\.\d+)*)')
FT_TGT_RE = re.compile(r'(?i)(?:figure|fig\.?|table)\s*\.?\s*(\d+(?:\.\d+)*)'
                       r'|[图表]\s*(\d+(?:\.\d+)*)')

VERDICT_PRIORITY = ['order_violation', 'missing_src', 'missing_tgt',
                    'marker_mismatch']


def read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read().replace('\r\n', '\n').replace('\r', '\n')


def parse_segments_file(path):
    """Parse source_segments.txt -> list of {'id','kind','text'} in order."""
    segs, cur = [], None
    for line in read_text(path).split('\n'):
        if line.startswith('#') and cur is None:
            continue  # header comment lines
        m = SEG_HEAD_RE.match(line)
        if m:
            cur = {'id': m.group(1), 'kind': m.group(2), 'lines': []}
            segs.append(cur)
            continue
        if cur is not None:
            cur['lines'].append(line)
    for s in segs:
        s['text'] = '\n'.join(s['lines']).strip('\n')
        del s['lines']
    return segs


def parse_bilingual(path):
    """Parse bilingual.md -> (order, blocks, duplicates).

    blocks: id -> {'kind', 'SRC': str|None, 'TGT': str|None, 'NOTE': str}
    """
    order, blocks, dups = [], {}, []
    cur_id, cur_mark = None, None
    for line in read_text(path).split('\n'):
        m = BID_RE.match(line)
        if m:
            sid = m.group(1)
            if sid in blocks:
                dups.append(sid)
            else:
                blocks[sid] = {'kind': m.group(2) or None,
                               'SRC': None, 'TGT': None, 'NOTE': []}
                order.append(sid)
            cur_id, cur_mark = sid, None
            continue
        mm = MARK_RE.match(line)
        if mm and cur_id:
            cur_mark = mm.group(1)
            if cur_mark in ('SRC', 'TGT') and blocks[cur_id][cur_mark] is None:
                blocks[cur_id][cur_mark] = []
            continue
        if cur_id and cur_mark:
            if cur_mark == 'NOTE':
                blocks[cur_id]['NOTE'].append(line)
            else:
                blocks[cur_id][cur_mark].append(line)
    for b in blocks.values():
        for k in ('SRC', 'TGT'):
            if b[k] is not None:
                b[k] = '\n'.join(b[k]).strip('\n')
        b['NOTE'] = '\n'.join(b['NOTE']).strip('\n')
    return order, blocks, dups


def ft_numbers_src(text):
    return Counter(m.group(1) for m in FT_SRC_RE.finditer(text))


def ft_numbers_tgt(text):
    out = Counter()
    for m in FT_TGT_RE.finditer(text):
        out[m.group(1) or m.group(2)] += 1
    return out


def marker_problems(kind, src, tgt):
    """Return a list of human-readable marker-parity problems."""
    problems = []
    # Equation segments: body must be unchanged (whitespace-normalized).
    if kind == 'equation':
        ns = re.sub(r'\s+', '', src)
        nt = re.sub(r'\s+', '', tgt)
        if ns not in nt:
            problems.append('equation body changed: expected %r in TGT' % src)
    # Figure/table numbers mentioned in SRC must appear in TGT.
    for num, cnt in (ft_numbers_src(src) - ft_numbers_tgt(tgt)).items():
        problems.append('figure/table number %r missing in TGT (x%d)' % (num, cnt))
    # Footnote markers [^id].
    for mark, cnt in (Counter(FN_RE.findall(src)) - Counter(FN_RE.findall(tgt))).items():
        problems.append('footnote marker %r missing in TGT (x%d)' % (mark, cnt))
    # Citation markers [12], [3,4], [5-7].
    for mark, cnt in (Counter(CIT_RE.findall(src)) - Counter(CIT_RE.findall(tgt))).items():
        problems.append('citation marker %r missing in TGT (x%d)' % (mark, cnt))
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description='Check bilingual alignment against the spine.')
    ap.add_argument('bilingual', help='bilingual.md in the paired-block format')
    ap.add_argument('segments', help='source_segments.txt from segment_source.py')
    ap.add_argument('--json', default=None, help='also write the report to this path')
    args = ap.parse_args(argv)
    try:
        src_segs = parse_segments_file(args.segments)
        order, blocks, dups = parse_bilingual(args.bilingual)
    except OSError as e:
        print('ERROR: %s' % e, file=sys.stderr)
        return 2
    if not src_segs:
        print('ERROR: no segments parsed from %s' % args.segments, file=sys.stderr)
        return 2

    src_index = {s['id']: i for i, s in enumerate(src_segs)}
    src_by_id = {s['id']: s for s in src_segs}

    # Order check: source-order indices of the bilingual file must increase.
    order_bad, max_seen = set(), -1
    for sid in order:
        idx = src_index.get(sid)
        if idx is None:
            continue
        if idx < max_seen:
            order_bad.add(sid)
        else:
            max_seen = idx

    unknown_ids = [sid for sid in order if sid not in src_index]

    verdicts = []
    tally = Counter()
    for s in src_segs:
        sid, kind = s['id'], s['kind']
        issues, details = [], []
        if sid not in blocks:
            issues.append('missing_tgt')
            details.append('segment absent from bilingual.md (dropped)')
        else:
            b = blocks[sid]
            if not b['SRC'] or not b['SRC'].strip():
                issues.append('missing_src')
                details.append('no > SRC block (or empty)')
            if not b['TGT'] or not b['TGT'].strip():
                issues.append('missing_tgt')
                details.append('no > TGT block (or empty)')
            elif b['SRC'] and b['SRC'].strip():
                probs = marker_problems(kind, b['SRC'], b['TGT'])
                if probs:
                    issues.append('marker_mismatch')
                    details.extend(probs)
            if sid in order_bad:
                issues.append('order_violation')
                details.append('appears out of source order in bilingual.md')
        verdict = 'ok'
        for v in VERDICT_PRIORITY:
            if v in issues:
                verdict = v
                break
        tally[verdict] += 1
        verdicts.append({'id': sid, 'kind': kind, 'verdict': verdict,
                         'details': details})

    status = 'pass'
    if tally['ok'] != len(src_segs) or dups or unknown_ids:
        status = 'fail'

    report = {
        'status': status,
        'bilingual_file': args.bilingual,
        'source_segments_file': args.segments,
        'summary': {
            'total_source_segments': len(src_segs),
            'ok': tally['ok'],
            'missing_tgt': tally['missing_tgt'],
            'missing_src': tally['missing_src'],
            'marker_mismatch': tally['marker_mismatch'],
            'order_violation': tally['order_violation'],
            'duplicate_ids': dups,
            'unknown_ids': unknown_ids,
        },
        'verdicts': verdicts,
    }
    out = json.dumps(report, ensure_ascii=False, indent=2)
    print(out)
    if args.json:
        try:
            with open(args.json, 'w', encoding='utf-8') as f:
                f.write(out + '\n')
        except OSError as e:
            print('ERROR: cannot write %s: %s' % (args.json, e), file=sys.stderr)
            return 2
    print('STATUS: %s' % status.upper(), file=sys.stderr)
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
