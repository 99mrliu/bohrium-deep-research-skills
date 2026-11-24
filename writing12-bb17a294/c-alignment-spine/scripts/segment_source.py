#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
segment_source.py — Split a source text/markdown file into stable-ID segments
and build a structure inventory.

The segment spine (对齐主干): every segment gets a stable ID
⟦S0001⟧, ⟦S0002⟧, ... in source order. IDs are never renumbered,
merged, or reordered downstream.

Usage:
    python3 segment_source.py SOURCE [-o OUTDIR]

Outputs (written to OUTDIR; default: the source file's directory):
    source_segments.txt       human-editable segment file
    structure_inventory.json  machine-readable structure inventory

Exit codes: 0 ok, 2 usage/IO error.
Stdlib only. No network.
"""
import argparse
import json
import os
import re
import sys

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
REFS_TITLE_RE = re.compile(r'^(references|bibliography|works\s+cited|参考文献)\b', re.I)
CAPTION_RE = re.compile(r'^(figure|fig\.?|table)\s*\.?\s*\d+', re.I)
FOOTNOTE_RE = re.compile(r'^\[\^[^\]]+\]\s*:')
LIST_RE = re.compile(r'^\s{0,3}([-*+]|\d{1,2}[.)])\s+\S')
FTNUM_RE = re.compile(r'(?i)\b(figure|fig\.?|table)\s*\.?\s*(\d+(?:\.\d+)*)')

# Words that are legitimate inside formulas and do not count as "prose".
MATH_FUNCS = {
    'sin', 'cos', 'tan', 'cot', 'sec', 'csc', 'log', 'ln', 'exp', 'max',
    'min', 'arg', 'det', 'sum', 'prod', 'frac', 'sqrt', 'infty', 'lim',
    'alpha', 'beta', 'gamma', 'delta', 'theta', 'lambda', 'sigma', 'phi',
    'omega', 'forall', 'exists', 'mathbb', 'mathrm', 'text', 'left',
    'right', 'cdot', 'times', 'leq', 'geq', 'neq', 'approx',
}


def looks_like_formula(text):
    """Heuristic: a single-line block that is math, not prose.

    True when the line contains math markers (= \\ ^ _) and at most two
    plain prose words (>=3 letters, not known math function names).
    Documented in references/method.md.
    """
    t = text.strip()
    if not t or '\n' in t:
        return False
    if not re.search(r'[=\\^_]', t):
        return False
    words = re.findall(r'[A-Za-z]{3,}', t)
    prose = [w for w in words if w.lower() not in MATH_FUNCS]
    return len(prose) <= 2


def segment_lines(lines):
    """Core splitter. Returns list of {'id','kind','text'} in source order."""
    segs = []
    in_refs = False
    i, n = 0, len(lines)

    def add(kind, text):
        segs.append({
            'id': 'S%04d' % (len(segs) + 1),
            'kind': kind,
            'text': text.rstrip(),
        })

    while i < n:
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        # HTML comments are metadata, never content.
        if s.startswith('<!--'):
            while '-->' not in lines[i] and i + 1 < n:
                i += 1
            i += 1
            continue
        # Headings (also toggle References-section mode).
        m = HEADING_RE.match(line)
        if m:
            title = m.group(2).strip()
            in_refs = bool(REFS_TITLE_RE.match(title))
            add('heading', line.rstrip())
            i += 1
            continue
        # Display math: $$...$$ or \[...\], possibly multi-line.
        if s.startswith('$$') or s.startswith('\\['):
            opener = '$$' if s.startswith('$$') else '\\['
            closer = '$$' if opener == '$$' else '\\]'
            rest = s[len(opener):]
            if closer in rest:
                add('equation', line.rstrip())
                i += 1
                continue
            buf = [line.rstrip()]
            i += 1
            while i < n:
                buf.append(lines[i].rstrip())
                done = closer in lines[i]
                i += 1
                if done:
                    break
            add('equation', '\n'.join(buf))
            continue
        # Footnote definitions: [^id]: text (+ indented continuation).
        if FOOTNOTE_RE.match(line):
            buf = [line.rstrip()]
            i += 1
            while i < n and (lines[i].startswith('    ') or lines[i].startswith('\t')):
                buf.append(lines[i].rstrip())
                i += 1
            add('footnote', '\n'.join(buf))
            continue
        # List items outside a References section: one segment per item line.
        if LIST_RE.match(line) and not in_refs:
            add('list_item', line.rstrip())
            i += 1
            continue
        # Generic block: gather until blank line or a structural boundary.
        buf = [line.rstrip()]
        i += 1
        while i < n and lines[i].strip() \
                and not HEADING_RE.match(lines[i]) \
                and not lines[i].strip().startswith('$$') \
                and not lines[i].strip().startswith('\\[') \
                and not FOOTNOTE_RE.match(lines[i]) \
                and not (LIST_RE.match(lines[i]) and not in_refs):
            buf.append(lines[i].rstrip())
            i += 1
        text = '\n'.join(buf)
        if in_refs:
            add('reference_entry', text)
        elif CAPTION_RE.match(text):
            add('caption', text)
        elif looks_like_formula(text):
            add('equation', text)
        else:
            add('paragraph', text)
    return segs


def build_inventory(segs, source_file):
    counts = {}
    ids_by_kind = {}
    sections, figures, tables = [], [], []
    equation_ids, reference_ids, footnote_ids = [], [], []
    current = None
    for sg in segs:
        k = sg['kind']
        counts[k] = counts.get(k, 0) + 1
        ids_by_kind.setdefault(k, []).append(sg['id'])
        if k == 'heading':
            m = HEADING_RE.match(sg['text'])
            level = len(m.group(1)) if m else 1
            title = m.group(2).strip() if m else sg['text'].strip()
            current = {'id': sg['id'], 'level': level,
                       'title': title, 'segment_ids': [sg['id']]}
            sections.append(current)
        elif current is not None:
            current['segment_ids'].append(sg['id'])
        # Figure/table numbers are inventoried from caption segments only.
        if k == 'caption':
            for mm in FTNUM_RE.finditer(sg['text']):
                label, num = mm.group(1).lower(), mm.group(2)
                rec = {'number': num, 'segment_id': sg['id'], 'label': mm.group(1)}
                (tables if label.startswith('tab') else figures).append(rec)
        if k == 'equation':
            equation_ids.append(sg['id'])
        if k == 'reference_entry':
            reference_ids.append(sg['id'])
        if k == 'footnote':
            footnote_ids.append(sg['id'])
    return {
        'source_file': os.path.basename(source_file),
        'segment_count': len(segs),
        'counts': counts,
        'ids_by_kind': ids_by_kind,
        'sections': sections,
        'figures': figures,
        'tables': tables,
        'equation_count': len(equation_ids),
        'equation_ids': equation_ids,
        'reference_entry_count': len(reference_ids),
        'reference_entry_ids': reference_ids,
        'footnote_ids': footnote_ids,
        'note': 'Never renumber, merge, drop, or reorder these segment IDs.',
    }


def write_segments_file(segs, path, source_file):
    lines = [
        '# source_segments.txt — generated by scripts/segment_source.py',
        '# Source: %s' % os.path.basename(source_file),
        '# Format: one header line "⟦S0001⟧ <kind>", then the segment text;',
        '# blocks are separated by exactly one blank line.',
        '# You may edit segment TEXT, but NEVER change IDs, kinds, or order.',
        '',
    ]
    for sg in segs:
        lines.append('⟦%s⟧ %s' % (sg['id'], sg['kind']))
        lines.append(sg['text'])
        lines.append('')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main(argv=None):
    ap = argparse.ArgumentParser(description='Segment a source file with stable IDs.')
    ap.add_argument('source', help='source text/markdown file (UTF-8)')
    ap.add_argument('-o', '--outdir', default=None,
                    help='output directory (default: source file directory)')
    args = ap.parse_args(argv)
    try:
        with open(args.source, 'r', encoding='utf-8') as f:
            text = f.read().replace('\r\n', '\n').replace('\r', '\n')
    except OSError as e:
        print('ERROR: cannot read %s: %s' % (args.source, e), file=sys.stderr)
        return 2
    outdir = args.outdir or os.path.dirname(os.path.abspath(args.source))
    os.makedirs(outdir, exist_ok=True)

    segs = segment_lines(text.split('\n'))
    inv = build_inventory(segs, args.source)

    seg_path = os.path.join(outdir, 'source_segments.txt')
    inv_path = os.path.join(outdir, 'structure_inventory.json')
    write_segments_file(segs, seg_path, args.source)
    with open(inv_path, 'w', encoding='utf-8') as f:
        json.dump(inv, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print('segments: %d  kinds: %s' % (len(segs), inv['counts']))
    print('figures: %s  tables: %s  equations: %d  references: %d' % (
        [x['number'] for x in inv['figures']],
        [x['number'] for x in inv['tables']],
        inv['equation_count'], inv['reference_entry_count']))
    print('wrote: %s' % seg_path)
    print('wrote: %s' % inv_path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
