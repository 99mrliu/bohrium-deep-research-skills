#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
derive_target.py — Derive the clean target-language file from the bilingual
master. The target is EXTRACTED, never retranslated (译文由母本派生，绝不重译).

It keeps only > TGT blocks, in spine order, strips segment IDs, and
preserves heading markup. With --inventory it also verifies that the
derived file covers every inventory item (sections, captions/figure-table
numbers, equations, reference entries).

Usage:
    python3 derive_target.py BILINGUAL [--segments source_segments.txt]
                             [--inventory structure_inventory.json]
                             [-o translation_target.md] [--json COV.json]

Exit codes: 0 pass (file written, coverage ok), 1 failures, 2 usage/IO error.
Stdlib only. No network.
"""
import argparse
import json
import os
import re
import sys

# Reuse the bilingual parser from check_alignment (same directory).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from check_alignment import (  # noqa: E402
    parse_bilingual, parse_segments_file, read_text, FT_TGT_RE,
)

FT_ANY_RE = FT_TGT_RE


def main(argv=None):
    ap = argparse.ArgumentParser(description='Derive clean target file from bilingual master.')
    ap.add_argument('bilingual', help='bilingual.md in the paired-block format')
    ap.add_argument('--segments', default=None,
                    help='source_segments.txt (gives canonical ID order; '
                         'default: order of appearance in bilingual.md)')
    ap.add_argument('--inventory', default=None,
                    help='structure_inventory.json for coverage verification')
    ap.add_argument('-o', '--out', default='translation_target.md',
                    help='output file (default: translation_target.md)')
    ap.add_argument('--json', default=None, help='also write coverage summary here')
    args = ap.parse_args(argv)

    try:
        order, blocks, dups = parse_bilingual(args.bilingual)
    except OSError as e:
        print('ERROR: %s' % e, file=sys.stderr)
        return 2
    if dups:
        print('ERROR: duplicate segment IDs in bilingual.md: %s' % dups,
              file=sys.stderr)
        return 2

    kinds = {sid: b['kind'] for sid, b in blocks.items()}
    if args.segments:
        try:
            src_segs = parse_segments_file(args.segments)
        except OSError as e:
            print('ERROR: %s' % e, file=sys.stderr)
            return 2
        spine_order = [s['id'] for s in src_segs]
        kinds.update({s['id']: s['kind'] for s in src_segs})
        extra = [sid for sid in order if sid not in set(spine_order)]
        if extra:
            print('ERROR: unknown IDs in bilingual.md: %s' % extra, file=sys.stderr)
            return 1
    else:
        spine_order = list(order)

    missing_tgt = [sid for sid in spine_order
                   if sid not in blocks
                   or not blocks[sid]['TGT'] or not blocks[sid]['TGT'].strip()]

    tgt_by_id = {sid: blocks[sid]['TGT'] for sid in spine_order if sid not in missing_tgt}
    derived_text = '\n\n'.join(tgt_by_id[sid] for sid in spine_order
                               if sid in tgt_by_id) + '\n'

    coverage = {}
    failures = []

    if args.inventory:
        try:
            inv = json.loads(read_text(args.inventory))
        except (OSError, ValueError) as e:
            print('ERROR: bad inventory %s: %s' % (args.inventory, e), file=sys.stderr)
            return 2

        # Sections: every heading segment has a TGT that still is a heading.
        secs = inv.get('sections', [])
        sec_ok = 0
        for sec in secs:
            t = tgt_by_id.get(sec['id'], '')
            if t.strip().startswith('#'):
                sec_ok += 1
            else:
                failures.append('section heading %s (%s) missing or lost markup'
                                % (sec['id'], sec.get('title', '')))
        coverage['sections'] = '%d/%d' % (sec_ok, len(secs))

        # Figures / tables: each inventoried number appears in derived text.
        for key, label in (('figures', 'figure'), ('tables', 'table')):
            items = inv.get(key, [])
            ok = 0
            for it in items:
                num = it['number']
                if any((m.group(1) or m.group(2)) == num
                       for m in FT_ANY_RE.finditer(derived_text)):
                    ok += 1
                else:
                    failures.append('%s number %s (segment %s) missing in target'
                                    % (label, num, it.get('segment_id')))
            coverage[key] = '%d/%d' % (ok, len(items))

        # Equations: every equation segment's SRC body survives (normalized)
        # in its TGT, and the segment has a TGT.
        eqs = inv.get('equation_ids', [])
        eq_ok = 0
        for sid in eqs:
            src = (blocks.get(sid) or {}).get('SRC') or ''
            tgt = tgt_by_id.get(sid, '')
            if tgt and re.sub(r'\s+', '', src) and \
                    re.sub(r'\s+', '', src) in re.sub(r'\s+', '', tgt):
                eq_ok += 1
            else:
                failures.append('equation %s missing or altered in target' % sid)
        coverage['equations'] = '%d/%d' % (eq_ok, len(eqs))

        # Reference entries: all inventoried entries have non-empty TGT.
        refs = inv.get('reference_entry_ids', [])
        ref_ok = sum(1 for sid in refs if tgt_by_id.get(sid, '').strip())
        if ref_ok != len(refs):
            failures.append('reference entries covered %d/%d' % (ref_ok, len(refs)))
        coverage['reference_entries'] = '%d/%d' % (ref_ok, len(refs))

        # Footnotes: all inventoried footnote definitions have TGT.
        fns = inv.get('footnote_ids', [])
        fn_ok = sum(1 for sid in fns if tgt_by_id.get(sid, '').strip())
        if fn_ok != len(fns):
            failures.append('footnote definitions covered %d/%d' % (fn_ok, len(fns)))
        coverage['footnotes'] = '%d/%d' % (fn_ok, len(fns))

    seg_total = len(spine_order)
    seg_ok = seg_total - len(missing_tgt)
    coverage['segments_with_tgt'] = '%d/%d' % (seg_ok, seg_total)

    status = 'pass' if not missing_tgt and not failures else 'fail'
    summary = {
        'status': status,
        'bilingual_file': args.bilingual,
        'output_file': args.out,
        'missing_tgt': missing_tgt,
        'coverage': coverage,
        'failures': failures,
    }

    if missing_tgt:
        summary['note'] = ('target file NOT written: these segments lack a '
                           '> TGT block; fix bilingual.md first')
        out_text = json.dumps(summary, ensure_ascii=False, indent=2)
        print(out_text)
        if args.json:
            with open(args.json, 'w', encoding='utf-8') as f:
                f.write(out_text + '\n')
        print('STATUS: FAIL', file=sys.stderr)
        return 1

    try:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(derived_text)
    except OSError as e:
        print('ERROR: cannot write %s: %s' % (args.out, e), file=sys.stderr)
        return 2

    out_text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(out_text)
    if args.json:
        try:
            with open(args.json, 'w', encoding='utf-8') as f:
                f.write(out_text + '\n')
        except OSError as e:
            print('ERROR: cannot write %s: %s' % (args.json, e), file=sys.stderr)
            return 2
    print('STATUS: %s' % status.upper(), file=sys.stderr)
    return 0 if status == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
