#!/usr/bin/env python3
"""Mine the case input into an evidence inventory (stdlib only).

Reads every file under --input-dir (default /input), classifies it, and
normalizes the material an agent needs for figure reading:

  * tables (CSV / TSV / delimiter-text) -> per-column numeric profile
    (count, min, max, unit guess parsed from the header, e.g. "Time (s)");
  * PDF -> text blocks per page via pdftotext (if available; the degraded
    path is recorded honestly in inventory.degraded);
  * markdown/text -> paragraphs with a line-level number index
    (every number keeps its verbatim context and locator);
  * images -> listed with pixel size (via PIL when importable).

Outputs <work>/inventory.json and a skeleton <out>/result.json that already
contains case_id and every output_contract field (all null, status partial),
so a valid partial deliverable exists from minute zero.

Usage:
  python mine_case.py --case /input/case.json --task /input/task.md \
      --input-dir /input --work /app/work --out /app/output
"""
import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys

IMG_EXT = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.gif', '.bmp', '.webp'}
PDF_EXT = {'.pdf'}
TABLE_EXT = {'.csv', '.tsv', '.txt', '.dat'}
TEXT_EXT = {'.md', '.tex', '.text'}
UNIT_RE = re.compile(r'[\(\[]([a-zA-Zµμ°Ω/%·*^0-9 .+-]+)[\)\]]\s*$')
UNIT_SUFFIXES = {'_pct': '%', '_percent': '%', '_ratio': None}
NUM_RE = re.compile(r'[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?')
PREFIXES = {'f': 1e-15, 'p': 1e-12, 'n': 1e-9, 'u': 1e-6, 'µ': 1e-6, 'μ': 1e-6,
            'm': 1e-3, 'c': 1e-2, 'd': 1e-1, 'k': 1e3, 'K': 1e3, 'M': 1e6,
            'G': 1e9, 'T': 1e12}


def contract_fields(contract):
    """Extract field names from any output_contract shape (dict/list/str)."""
    fields = []
    if isinstance(contract, dict):
        for k, v in contract.items():
            fields.append(k)
            sub = v.get('fields') if isinstance(v, dict) else None
            if isinstance(sub, dict):
                fields.extend(sub.keys())
            elif isinstance(sub, list):
                fields.extend(contract_fields(sub))
    elif isinstance(contract, list):
        for item in contract:
            if isinstance(item, str):
                fields.append(item)
            elif isinstance(item, dict):
                name = item.get('name') or item.get('field') or item.get('key')
                if name:
                    fields.append(name)
    seen, out = set(), []
    for f in fields:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


def guess_unit(header):
    """Parse a unit out of a column header: parenthesized/bracketed tail
    ('Current (mA)', 'Time [s]') or a known suffix ('rate_pct' -> '%').
    Bare words are never treated as units."""
    if not header:
        return None
    h = header.strip().strip('"')
    m = UNIT_RE.search(h)
    if m:
        unit = m.group(1).strip()
        if unit and unit.lower() not in ('x', 'y'):
            return unit
    low = h.lower()
    for suf, unit in UNIT_SUFFIXES.items():
        if low.endswith(suf):
            return unit
    return None


def prefix_scale(unit):
    """Return (magnitude, base_unit) for prefixed units like mV -> (1e-3, V)."""
    if not unit:
        return 1.0, unit
    for p in ('µ', 'μ'):
        if unit.startswith(p):
            return PREFIXES[p], unit[1:]
    if unit[0] in PREFIXES:
        return PREFIXES[unit[0]], unit[1:]
    return 1.0, unit


def sniff_delimiter(sample, path):
    if path.endswith('.tsv'):
        return '\t'
    try:
        return csv.Sniffer().sniff(sample, delimiters=',;\t|').delimiter
    except csv.Error:
        return ','


def parse_table(path):
    """Parse a delimiter table into a column profile. Returns None if not a
    rectangular numeric-ish table."""
    raw = open(path, encoding='utf-8', errors='replace').read()
    if not raw.strip():
        return None
    sample = raw[:4096]
    delim = sniff_delimiter(sample, path)
    try:
        rows = list(csv.reader(io.StringIO(raw), delimiter=delim))
    except csv.Error:
        return None
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 2 or not (2 <= len(rows[0]) <= 40):
        return None
    width = max(len(r) for r in rows[:20])
    header = rows[0]
    if len(header) < width:
        header = header + ['col%d' % (i + 1) for i in range(len(header), width)]
    cols = {}
    for ci in range(width):
        vals = []
        for r in rows[1:]:
            cell = r[ci].strip() if ci < len(r) else ''
            try:
                vals.append(float(cell))
            except ValueError:
                pass
        if vals:
            name = header[ci].strip() or 'col%d' % (ci + 1)
            cols[name] = {
                'n': len(vals),
                'min': min(vals),
                'max': max(vals),
                'mean': sum(vals) / len(vals),
                'unit_guess': guess_unit(name),
                'first_values': vals[:3],
            }
    if not cols:
        return None
    return {'columns': cols, 'n_rows': len(rows) - 1,
            'header': [h.strip() for h in header[:width]]}


def number_index_text(text, locator_prefix):
    """Index numbers with verbatim context lines."""
    index = []
    for ln, line in enumerate(text.splitlines(), 1):
        for m in NUM_RE.finditer(line):
            index.append({
                'number': m.group(0),
                'locator': '%s#line-%d' % (locator_prefix, ln),
                'context': line.strip()[:240],
            })
    return index


def pdf_blocks(path):
    """Extract per-page text blocks with pdftotext; [] if unavailable."""
    try:
        out = subprocess.run(
            ['pdftotext', '-layout', path, '-'],
            capture_output=True, text=True, timeout=120)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    pages = out.stdout.split('\f')
    blocks = []
    for pi, page in enumerate(pages, 1):
        for para in re.split(r'\n\s*\n', page):
            para = ' '.join(para.split())
            if len(para) >= 40:
                blocks.append({'page': pi, 'kind': 'pdf_block', 'text': para})
    return blocks


def image_size(path):
    try:
        from PIL import Image
        with Image.open(path) as im:
            return {'width': im.width, 'height': im.height}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--case', default='/input/case.json')
    ap.add_argument('--task', default='/input/task.md')
    ap.add_argument('--input-dir', default='/input')
    ap.add_argument('--work', default='/app/work')
    ap.add_argument('--out', default='/app/output')
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.out, exist_ok=True)

    case = {}
    if os.path.exists(args.case):
        case = json.load(open(args.case, encoding='utf-8'))
    case_id = case.get('case_id') or case.get('caseId') or case.get('id')
    fields = contract_fields(case.get('output_contract') or {})

    inv = {'case_id': case_id, 'files': [], 'tables': {}, 'text_blocks': [],
           'number_index': [], 'figures': [], 'degraded': [],
           'generated_by': 'mine_case.py'}
    for root, _dirs, names in os.walk(args.input_dir):
        for name in sorted(names):
            p = os.path.join(root, name)
            rel = os.path.relpath(p, args.input_dir)
            ext = os.path.splitext(name)[1].lower()
            entry = {'path': rel, 'size': os.path.getsize(p)}
            if ext in TABLE_EXT:
                prof = parse_table(p)
                if prof:
                    entry['kind'] = 'table'
                    inv['tables'][rel] = prof
                else:
                    entry['kind'] = 'text'
                    text = open(p, encoding='utf-8', errors='replace').read()
                    inv['text_blocks'].append(
                        {'file': rel, 'kind': 'text_block',
                         'text': ' '.join(text.split())[:2000]})
                    inv['number_index'].extend(
                        number_index_text(text, rel))
            elif ext in PDF_EXT:
                entry['kind'] = 'pdf'
                blocks = pdf_blocks(p)
                if blocks is None:
                    inv['degraded'].append(
                        {'file': rel,
                         'reason': 'pdftotext unavailable or failed; '
                                   'read the PDF with the platform pdf tool'})
                else:
                    inv['text_blocks'].extend(
                        dict(b, file=rel) for b in blocks)
                    inv['number_index'].extend(
                        number_index_text('\n'.join(b['text'] for b in blocks),
                                          rel))
            elif ext in IMG_EXT:
                entry['kind'] = 'figure'
                entry.update(image_size(p))
                inv['figures'].append(rel)
            elif ext in TEXT_EXT or ext in {'.json'}:
                entry['kind'] = 'text'
                if ext != '.json':
                    text = open(p, encoding='utf-8', errors='replace').read()
                    inv['text_blocks'].append(
                        {'file': rel, 'kind': 'text_block',
                         'text': ' '.join(text.split())[:2000]})
                    inv['number_index'].extend(
                        number_index_text(text, rel))
            else:
                entry['kind'] = 'other'
            inv['files'].append(entry)

    if os.path.exists(args.task):
        text = open(args.task, encoding='utf-8', errors='replace').read()
        inv['task_text'] = text
        inv['number_index'].extend(number_index_text(text, 'task.md'))

    inv_path = os.path.join(args.work, 'inventory.json')
    with open(inv_path, 'w', encoding='utf-8') as f:
        json.dump(inv, f, ensure_ascii=False, indent=2)

    # skeleton result.json: valid partial from minute zero
    result = {'case_id': case_id, 'status': 'partial',
              'status_reason': 'skeleton written by mine_case.py before '
                               'analysis; fields are null until filled',
              'sources': [], 'uncertainty': []}
    for fld in fields:
        result.setdefault(fld, None)
    result_path = os.path.join(args.out, 'result.json')
    with open(result_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        'inventory': inv_path, 'result_skeleton': result_path,
        'case_id': case_id, 'contract_fields': fields,
        'tables': sorted(inv['tables']),
        'figures': inv['figures'],
        'text_blocks': len(inv['text_blocks']),
        'numbers_indexed': len(inv['number_index']),
        'degraded': inv['degraded'],
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
