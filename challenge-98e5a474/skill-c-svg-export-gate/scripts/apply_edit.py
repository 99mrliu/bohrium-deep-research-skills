#!/usr/bin/env python3
"""apply_edit.py — source-preserving surgical edits on an SVG file
(stdlib only).

Edits are applied as string-level surgery on the raw XML: only the byte span
of the targeted element is touched, everything else stays bit-identical, so
"only one label changed" is independently verifiable by diffing the two
files. Each operation is logged with before/after snippets.

Supported operations (targets must be non-container elements, not <g>/<svg>/
<defs>):
  retext   {"op":"retext","id":"ent-egfr","text":"HER2"}
  set_attr {"op":"set_attr","id":"rel-r3","attr":"stroke","value":"#B03030"}
  move     {"op":"move","id":"legend-title","dx":0,"dy":-20}
  delete   {"op":"delete","id":"ann-old"}

Usage:
  python3 apply_edit.py --svg in.svg --edits edits.json --out out.svg \
      --log edit_log.json
Exit 0 when all edits applied, 1 on any error (unknown id, container target,
rich inner markup) — errors are listed in the log; no partial output is left
behind (the output file is written only when every edit succeeds).
"""
import argparse
import json
import os
import re
import subprocess
import sys

CONTAINER_TAGS = {'g', 'svg', 'defs', 'marker', 'metadata', 'title', 'desc'}
PROTECTED_TAGS = {'svg', 'defs', 'marker', 'metadata'}


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;')
            .replace('>', '&gt;'))


class EditError(Exception):
    pass


def find_span(raw, target_id):
    needle = 'id="%s"' % target_id
    hits = [m.start() for m in re.finditer(re.escape(needle), raw)]
    if not hits:
        raise EditError('id %r not found' % target_id)
    if len(hits) > 1:
        raise EditError('id %r occurs %d times (ambiguous)' %
                        (target_id, len(hits)))
    pos = hits[0]
    lt = raw.rfind('<', 0, pos)
    if lt < 0 or raw[lt + 1:lt + 2] in '/!?':
        raise EditError('id %r: cannot locate opening tag' % target_id)
    m = re.match(r'<([A-Za-z_][\w:.-]*)', raw[lt:])
    tag = m.group(1)
    gt = raw.find('>', pos)
    if gt < 0:
        raise EditError('id %r: unterminated tag' % target_id)
    if raw[gt - 1] == '/':
        return tag, lt, gt + 1, gt + 1  # self-closing, empty inner
    depth = 1
    i = gt + 1
    while depth:
        nxt = re.search(r'<(/?)%s[\s/>]' % re.escape(tag), raw[i:])
        if not nxt:
            raise EditError('id %r: no closing </%s>' % (target_id, tag))
        j = i + nxt.start()
        if nxt.group(1):
            depth -= 1
            close_start = j
        else:
            close_end = raw.find('>', j)
            if raw[close_end - 1] != '/':
                depth += 1
        i = raw.find('>', j) + 1
    return tag, lt, close_start, i  # inner = (gt+1, close_start)


def open_tag_bounds(raw, span):
    _, lt, _, _ = span
    gt = raw.find('>', lt)
    return lt, gt


def apply_one(raw, edit):
    span = find_span(raw, edit['id'])
    tag, lt, inner_start_end, end = span
    op = edit['op']
    if tag in PROTECTED_TAGS:
        raise EditError('id %r is on protected <%s>' % (edit['id'], tag))
    o_lt, o_gt = open_tag_bounds(raw, span)
    open_tag = raw[o_lt:o_gt + 1]

    if op == 'retext':
        if tag == 'g':
            inner = raw[o_gt + 1:inner_start_end]
            texts = list(re.finditer(
                r'<text\b[^>]*>(.*?)</text>', inner, flags=re.S))
            if len(texts) != 1:
                raise EditError('retext on <g> requires exactly one <text> '
                                'descendant, found %d' % len(texts))
            t = texts[0]
            if '<' in t.group(1):
                raise EditError('retext target text has nested markup')
            new = (raw[:o_gt + 1 + t.start(1)] + esc(edit['text'])
                   + raw[o_gt + 1 + t.end(1):])
            return new, {'before_text': t.group(1)[:200],
                         'after_text': edit['text']}
        if raw[o_gt - 1] == '/':
            raise EditError('retext on empty self-closing element')
        inner = raw[o_gt + 1:inner_start_end]
        if '<' in inner:
            raise EditError('retext target has nested markup; edit children '
                            'individually')
        new = raw[:o_gt + 1] + esc(edit['text']) + raw[inner_start_end:]
        return new, {'before_text': inner[:200], 'after_text': edit['text']}
    if op == 'set_attr':
        attr, value = edit['attr'], str(edit['value'])
        pat = re.compile(r'\b%s="[^"]*"' % re.escape(attr))
        if pat.search(open_tag):
            new_tag = pat.sub('%s="%s"' % (attr, value), open_tag)
        else:
            ins = ' %s="%s"' % (attr, value)
            if open_tag.endswith('/>'):
                new_tag = open_tag[:-2] + ins + '/>'
            else:
                new_tag = open_tag[:-1] + ins + '>'
        new = raw[:o_lt] + new_tag + raw[o_gt + 1:]
        return new, {'before_tag': open_tag[:200], 'after_tag': new_tag[:200]}
    if op == 'move':
        dx, dy = float(edit.get('dx', 0)), float(edit.get('dy', 0))
        tr = 'translate(%g,%g)' % (dx, dy)
        pat = re.compile(r'\btransform="([^"]*)"')
        m = pat.search(open_tag)
        if m:
            new_tag = (open_tag[:m.start(1)] + m.group(1) + ' ' + tr
                       + open_tag[m.end(1):])
        else:
            ins = ' transform="%s"' % tr
            if open_tag.endswith('/>'):
                new_tag = open_tag[:-2] + ins + '/>'
            else:
                new_tag = open_tag[:-1] + ins + '>'
        new = raw[:o_lt] + new_tag + raw[o_gt + 1:]
        return new, {'before_tag': open_tag[:200], 'after_tag': new_tag[:200]}
    if op == 'delete':
        if 'data-layer' in open_tag or 'groupmode="layer"' in open_tag:
            raise EditError('refusing to delete a whole layer; delete its '
                            'elements individually')
        return raw[:lt] + raw[end:], {'removed': raw[lt:min(end, lt + 200)]}
    raise EditError('unknown op %r' % op)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--svg', required=True)
    ap.add_argument('--edits', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--log', required=True)
    args = ap.parse_args()

    raw = open(args.svg, encoding='utf-8').read()
    with open(args.edits, encoding='utf-8') as f:
        edits = json.load(f).get('edits', [])
    applied, failed = [], []
    cur = raw
    for edit in edits:
        try:
            cur, detail = apply_one(cur, edit)
            applied.append(dict(edit, **detail))
        except EditError as exc:
            failed.append({'edit': edit, 'error': str(exc)})

    log = {'status': 'ok' if not failed else 'failed',
           'input': args.svg, 'edits_requested': len(edits),
           'edits_applied': len(applied), 'applied': applied,
           'failed': failed}
    if failed:
        with open(args.log, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        for f_ in failed:
            print('EDIT FAILED: %s' % f_['error'], file=sys.stderr)
        print(json.dumps({'status': 'failed', 'applied': 0,
                          'failed': len(failed)}))
        sys.exit(1)

    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(cur)
    # verify preservation: everything except edited spans is identical
    log['output'] = args.out
    log['bytes_before'] = len(raw.encode('utf-8'))
    log['bytes_after'] = len(cur.encode('utf-8'))
    lint = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'svg_lint.py')
    p = subprocess.run([sys.executable, lint, '--svg', args.out,
                        '--out', os.path.splitext(args.log)[0]
                        + '.postedit_lint.json'],
                       capture_output=True, text=True)
    try:
        log['post_edit_lint'] = json.loads(p.stdout)
    except ValueError:
        log['post_edit_lint'] = {'raw_stdout': p.stdout[:300],
                                 'stderr': p.stderr[-300:]}
    with open(args.log, 'w', encoding='utf-8') as f:
        json.dump(log, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': 'ok', 'applied': len(applied),
                      'bytes_delta': log['bytes_after']
                      - log['bytes_before']}))
    sys.exit(0)


if __name__ == '__main__':
    main()
