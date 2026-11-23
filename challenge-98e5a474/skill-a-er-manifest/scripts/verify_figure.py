#!/usr/bin/env python3
"""verify_figure.py — reconcile a rendered SVG against its entity-relation
manifest, including an anti-hallucination gate (stdlib only).

Checks (all must pass):
  1. every manifest entity appears exactly once in the SVG (data-entity id,
     label text, class attribute agree with the manifest);
  2. every manifest relation appears exactly once (data-relation id with the
     same from/to/type — i.e. direction and interaction semantics match);
  3. every visible <text> string in the SVG is traceable: it must equal the
     figure title, an entity/group/edge/legend label, or a declared
     annotation — any other text is reported as hallucinated content;
  4. every manifest entity/relation carries a non-empty evidence.locator.

Usage:
  python3 verify_figure.py --manifest m.json --svg figure.svg \
      --out verification_report.json
Exit code 0 = pass, 1 = fail (details in the JSON report).
"""
import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

NS = '{http://www.w3.org/2000/svg}'
_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, '..', 'resources', 'classes_default.json'),
          encoding='utf-8') as _f:
    DEFAULT_CLASSES = json.load(_f)


def collect_texts(root):
    texts = []
    for el in root.iter():
        if el.tag == NS + 'text' or el.tag == 'text':
            s = ''.join(el.itertext()).strip()
            if s:
                texts.append(s)
    return texts


def data_elements(root, attr):
    found = {}
    for el in root.iter():
        v = el.attrib.get(attr)
        if v:
            found.setdefault(v, []).append(el)
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--svg', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    with open(args.manifest, encoding='utf-8') as f:
        m = json.load(f)
    tree = ET.parse(args.svg)
    root = tree.getroot()

    checks = []
    failures = []

    # --- entities -------------------------------------------------------
    ent_els = data_elements(root, 'data-entity')
    for e in m['entities']:
        els = ent_els.get(e['id'], [])
        if len(els) != 1:
            failures.append('entity %s appears %d times (want 1)'
                            % (e['id'], len(els)))
            continue
        el = els[0]
        if el.attrib.get('data-label') != e['label']:
            failures.append('entity %s label mismatch: svg=%r manifest=%r'
                            % (e['id'], el.attrib.get('data-label'), e['label']))
        if el.attrib.get('data-class') != e['class']:
            failures.append('entity %s class mismatch: svg=%r manifest=%r'
                            % (e['id'], el.attrib.get('data-class'), e['class']))
        ev = e.get('evidence') or {}
        if not ev.get('locator'):
            failures.append('entity %s has empty evidence.locator' % e['id'])
    extra_ent = sorted(set(ent_els) - {e['id'] for e in m['entities']})
    if extra_ent:
        failures.append('SVG contains entities absent from manifest: %s'
                        % ', '.join(extra_ent))
    checks.append({'name': 'entities_present_once_with_label_and_class',
                   'checked': len(m['entities'])})

    # --- relations ------------------------------------------------------
    rel_els = data_elements(root, 'data-relation')
    edge_rels = [r for r in m.get('relations', []) if r['type'] != 'contains']
    for r in edge_rels:
        els = rel_els.get(r['id'], [])
        if len(els) != 1:
            failures.append('relation %s appears %d times (want 1)'
                            % (r['id'], len(els)))
            continue
        el = els[0]
        for k, key in (('data-from', 'from'), ('data-to', 'to'),
                       ('data-type', 'type')):
            if el.attrib.get(k) != r[key]:
                failures.append('relation %s %s mismatch: svg=%r manifest=%r'
                                % (r['id'], key, el.attrib.get(k), r[key]))
        ev = r.get('evidence') or {}
        if not ev.get('locator'):
            failures.append('relation %s has empty evidence.locator' % r['id'])
    extra_rel = sorted(set(rel_els) - {r['id'] for r in edge_rels})
    if extra_rel:
        failures.append('SVG contains relations absent from manifest: %s'
                        % ', '.join(extra_rel))
    checks.append({'name': 'relations_present_once_with_direction_and_type',
                   'checked': len(edge_rels)})

    # --- anti-hallucination text gate -----------------------------------
    allowed = set()
    title = (m['figure'].get('title') or '').strip()
    if title:
        allowed.add(title)
    allowed.add('Legend')
    for e in m['entities']:
        allowed.add(e['label'].strip())
    for g in m.get('groups', []):
        allowed.add((g.get('label') or '').strip())
    for r in edge_rels:
        if r.get('label'):
            allowed.add(r['label'].strip())
        if r['type'] == 'unclear':
            allowed.add('?')
    used_classes = []
    for e in m['entities']:
        if e['class'] not in used_classes:
            used_classes.append(e['class'])
    classes = dict(DEFAULT_CLASSES)
    classes.update(m.get('classes') or {})
    for cname in used_classes:
        allowed.add((classes.get(cname, {}).get('label') or cname).strip())
    for tname in {r['type'] for r in edge_rels}:
        allowed.add(tname)
    for a in m.get('annotations', []):
        allowed.add((a.get('text') or '').strip())
    allowed.discard('')

    svg_texts = collect_texts(root)
    hallucinated = [t for t in svg_texts if t not in allowed]
    if hallucinated:
        failures.append('untraceable text in SVG (not in manifest): %r'
                        % sorted(set(hallucinated)))
    missing_text = [t for t in sorted(allowed)
                    if t and t not in svg_texts and t != 'Legend']
    if missing_text:
        failures.append('manifest labels missing from SVG: %r' % missing_text)
    checks.append({'name': 'anti_hallucination_text_gate',
                   'svg_text_spans': len(svg_texts),
                   'allowed_strings': len(allowed)})

    report = {'status': 'pass' if not failures else 'fail',
              'manifest': args.manifest,
              'svg': args.svg,
              'checks': checks,
              'failures': failures,
              'summary': {'entities': len(m['entities']),
                          'relations': len(edge_rels),
                          'svg_text_spans': len(svg_texts),
                          'untraceable_texts': sorted(set(hallucinated))}}
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps({'status': report['status'],
                      'failures': len(failures)}, ensure_ascii=False))
    if failures:
        for f_ in failures:
            print('FAIL: ' + f_, file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
