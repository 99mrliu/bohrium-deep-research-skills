#!/usr/bin/env python3
"""render_manifest.py — deterministic renderer: entity-relation manifest ->
layered, editable SVG (stdlib only, no third-party imports).

The script contains no scientific judgement: every entity, relation, label,
color and annotation it draws comes from the manifest, and every drawn element
carries data-* attributes so verify_figure.py can reconcile the SVG against
the manifest afterwards. Layout precedence per entity: explicit box > grid
(col,row) > automatic topological layering.

Usage:
  python3 render_manifest.py --manifest m.json --svg figure.svg \
      --report render_report.json
Exit code 0 on success (layout warnings are reported, not fatal); 1 on a
manifest error (unknown type/class, dangling endpoint, missing evidence).
"""
import argparse
import hashlib
import html
import json
import math
import os
import sys

VERSION = '1.0'
_HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(_HERE, '..', 'resources', 'classes_default.json'),
          encoding='utf-8') as _f:
    DEFAULT_CLASSES = json.load(_f)
FONT = 'Helvetica, Arial, sans-serif'
GRID_COL_W, GRID_ROW_H = 210, 120
MARGIN_X, MARGIN_Y = 70, 90
BOX_W, BOX_H = 140, 50
GROUP_PAD = 26

REL_STYLE = {
    'activates':    {'dash': None,     'marker': 'arrow',      'glyph': 'activates'},
    'inhibits':     {'dash': None,     'marker': 'tbar',       'glyph': 'inhibits'},
    'binds':        {'dash': None,     'marker': 'dot',        'glyph': 'binds'},
    'produces':     {'dash': None,     'marker': 'arrow_open', 'glyph': 'produces'},
    'degrades':     {'dash': None,     'marker': 'arrow_x',    'glyph': 'degrades'},
    'translocates': {'dash': '6,3',    'marker': 'arrow',      'glyph': 'translocates'},
    'modifies':     {'dash': None,     'marker': 'arrow',      'glyph': 'modifies'},
    'unclear':      {'dash': '3,3',    'marker': 'arrow_open', 'glyph': 'unclear'},
}


def esc(s):
    return html.escape(str(s), quote=True)


class ManifestError(Exception):
    pass


def load_manifest(path):
    with open(path, encoding='utf-8') as f:
        m = json.load(f)
    for key in ('figure', 'entities'):
        if key not in m:
            raise ManifestError('manifest missing top-level key: ' + key)
    ids = set()
    for e in m['entities']:
        for k in ('id', 'label', 'class'):
            if k not in e:
                raise ManifestError('entity missing %s: %r' % (k, e))
        if e['id'] in ids:
            raise ManifestError('duplicate entity id: ' + e['id'])
        ids.add(e['id'])
        ev = e.get('evidence') or {}
        if not ev.get('locator') or not ev.get('quote'):
            raise ManifestError('entity %s lacks evidence.locator/quote' % e['id'])
    classes = dict(DEFAULT_CLASSES)
    classes.update(m.get('classes') or {})
    for e in m['entities']:
        if e['class'] not in classes:
            classes[e['class']] = {'color': '#8C8C8C', 'label': e['class']}
    m['classes'] = classes
    for r in m.get('relations', []):
        if r.get('type') not in REL_STYLE and r.get('type') != 'contains':
            raise ManifestError('relation %r has unknown type %r'
                                % (r.get('id'), r.get('type')))
        for end in ('from', 'to'):
            if r.get(end) not in ids and not any(
                    g['id'] == r.get(end) for g in m.get('groups', [])):
                raise ManifestError('relation %r dangling endpoint %r'
                                    % (r.get('id'), r.get(end)))
        ev = r.get('evidence') or {}
        if not ev.get('locator') or not ev.get('quote'):
            raise ManifestError('relation %r lacks evidence' % r.get('id'))
    return m


def auto_layers(m):
    """Longest-path layering over directed relations; cycles fall back to 0."""
    succ = {e['id']: [] for e in m['entities']}
    for r in m.get('relations', []):
        if r['type'] != 'contains' and r['from'] in succ and r['to'] in succ \
                and r['from'] != r['to']:
            succ[r['from']].append(r['to'])
    depth, visiting = {}, set()

    def dfs(u):
        if u in depth:
            return depth[u]
        if u in visiting:
            return 0
        visiting.add(u)
        d = 0
        for v in succ[u]:
            d = max(d, dfs(v) + 1)
        visiting.discard(u)
        depth[u] = d
        return d

    for e in m['entities']:
        dfs(e['id'])
    rows = {}
    for e in m['entities']:
        c = depth[e['id']]
        rows[c] = rows.get(c, 0) + 1
        e['_grid'] = (c, rows[c] - 1)


def layout(m):
    auto_layers(m)
    boxes = {}
    for e in m['entities']:
        if 'box' in e:
            b = e['box']
            boxes[e['id']] = (float(b['x']), float(b['y']),
                              float(b['w']), float(b['h']))
        else:
            c, r = (e['grid']['col'], e['grid']['row']) if 'grid' in e \
                else e['_grid']
            boxes[e['id']] = (MARGIN_X + c * GRID_COL_W,
                              MARGIN_Y + r * GRID_ROW_H, BOX_W, BOX_H)
    group_boxes = {}
    for g in m.get('groups', []):
        if 'box' in g:
            b = g['box']
            group_boxes[g['id']] = (float(b['x']), float(b['y']),
                                    float(b['w']), float(b['h']))
        else:
            members = [boxes[i] for i in g['members'] if i in boxes]
            if not members:
                raise ManifestError('group %r has no known members' % g['id'])
            x0 = min(b[0] for b in members) - GROUP_PAD
            y0 = min(b[1] for b in members) - GROUP_PAD - 16
            x1 = max(b[0] + b[2] for b in members) + GROUP_PAD
            y1 = max(b[1] + b[3] for b in members) + GROUP_PAD
            group_boxes[g['id']] = (x0, y0, x1 - x0, y1 - y0)
    return boxes, group_boxes


def border_point(box, tx, ty):
    """Intersection of the ray box-center -> (tx,ty) with the box border."""
    x, y, w, h = box
    cx, cy = x + w / 2.0, y + h / 2.0
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (w / 2.0) / abs(dx) if dx else float('inf')
    sy = (h / 2.0) / abs(dy) if dy else float('inf')
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def svg_header(w, h):
    return ('<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd" '
            'width="%d" height="%d" viewBox="0 0 %d %d" version="1.1">\n'
            % (w, h, w, h))


def markers_def():
    d = ['<defs>']
    d.append('<marker id="mk-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
             'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             '<path d="M0,0 L10,5 L0,10 z" fill="#333333"/></marker>')
    d.append('<marker id="mk-arrow-open" viewBox="0 0 10 10" refX="9" refY="5" '
             'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
             '<path d="M0,0 L10,5 L0,10" fill="none" stroke="#333333" '
             'stroke-width="1.4"/></marker>')
    d.append('<marker id="mk-tbar" viewBox="0 0 10 12" refX="8" refY="6" '
             'markerWidth="7" markerHeight="9" orient="auto">'
             '<path d="M8,0 L8,12" stroke="#333333" stroke-width="2.2"/></marker>')
    d.append('<marker id="mk-dot" viewBox="0 0 8 8" refX="4" refY="4" '
             'markerWidth="6" markerHeight="6">'
             '<circle cx="4" cy="4" r="3" fill="#333333"/></marker>')
    d.append('<marker id="mk-arrow-x" viewBox="0 0 12 12" refX="6" refY="6" '
             'markerWidth="8" markerHeight="8" orient="auto">'
             '<path d="M1,1 L11,11 M11,1 L1,11" stroke="#B03030" '
             'stroke-width="1.8"/></marker>')
    d.append('</defs>')
    return '\n'.join(d)


def layer_open(name):
    return ('<g id="layer-%s" data-layer="%s" inkscape:groupmode="layer" '
            'inkscape:label="%s">' % (name, name, name))


def render(m):
    boxes, group_boxes = layout(m)
    canvas = m['figure'].get('canvas') or {}
    cw = int(canvas.get('width', 1000))
    ch = int(canvas.get('height', 640))
    warnings = []

    need_w = need_h = 0
    for (x, y, w, h) in list(boxes.values()) + list(group_boxes.values()):
        need_w = max(need_w, x + w + 40)
        need_h = max(need_h, y + h + 40)
    cw = max(cw, int(math.ceil(need_w)))
    ch = max(ch, int(math.ceil(need_h)) + 120)  # legend strip

    ids = list(boxes)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = boxes[ids[i]], boxes[ids[j]]
            if (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                    and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]):
                warnings.append('overlap: %s vs %s' % (ids[i], ids[j]))

    used_classes = []
    for e in m['entities']:
        if e['class'] not in used_classes:
            used_classes.append(e['class'])
    used_types = []
    for r in m.get('relations', []):
        if r['type'] != 'contains' and r['type'] not in used_types:
            used_types.append(r['type'])

    out = [svg_header(cw, ch)]
    out.append('<title>%s</title>' % esc(m['figure'].get('title', 'figure')))
    src = m['figure'].get('source') or {}
    prov = {'generator': 'render_manifest.py v' + VERSION,
            'source': src,
            'manifest_sha256': hashlib.sha256(
                json.dumps(m, sort_keys=True).encode('utf-8')).hexdigest()}
    out.append('<metadata id="figure-provenance">%s</metadata>'
               % esc(json.dumps(prov, ensure_ascii=False)))
    out.append(markers_def())

    out.append(layer_open('background'))
    out.append('<rect id="bg" x="0" y="0" width="%d" height="%d" fill="#FFFFFF"/>'
               % (cw, ch))
    out.append('</g>')

    out.append(layer_open('groups'))
    for g in m.get('groups', []):
        x, y, w, h = group_boxes[g['id']]
        out.append('<g id="grp-%s" data-group="%s">' % (esc(g['id']), esc(g['id'])))
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="10" '
                   'fill="#F4F4F4" fill-opacity="0.55" stroke="#888888" '
                   'stroke-width="1" stroke-dasharray="5,3"/>' % (x, y, w, h))
        out.append('<text id="grp-%s-label" data-label="%s" x="%.1f" y="%.1f" '
                   'font-family="%s" font-size="12" fill="#555555">%s</text>'
                   % (esc(g['id']), esc(g['label']), x + 8, y + 15, FONT,
                      esc(g['label'])))
        out.append('</g>')
    out.append('</g>')

    out.append(layer_open('relations'))
    edge_labels = []
    for r in m.get('relations', []):
        if r['type'] == 'contains':
            continue
        st = REL_STYLE[r['type']]
        fb = boxes.get(r['from']) or group_boxes.get(r['from'])
        tb = boxes.get(r['to']) or group_boxes.get(r['to'])
        fcx, fcy = fb[0] + fb[2] / 2.0, fb[1] + fb[3] / 2.0
        tcx, tcy = tb[0] + tb[2] / 2.0, tb[1] + tb[3] / 2.0
        x1, y1 = border_point(fb, tcx, tcy)
        x2, y2 = border_point(tb, fcx, fcy)
        dash = ' stroke-dasharray="%s"' % st['dash'] if st['dash'] else ''
        marker = {'arrow': 'mk-arrow', 'arrow_open': 'mk-arrow-open',
                  'tbar': 'mk-tbar', 'dot': 'mk-dot',
                  'arrow_x': 'mk-arrow-x'}[st['marker']]
        if st['marker'] == 'arrow_x':
            line_marker = ' marker-end="url(#mk-arrow)"'
        else:
            line_marker = ' marker-end="url(#%s)"' % marker
        out.append('<g id="rel-%s" data-relation="%s" data-type="%s" '
                   'data-from="%s" data-to="%s">'
                   % (esc(r['id']), esc(r['id']), esc(r['type']),
                      esc(r['from']), esc(r['to'])))
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                   'stroke="#333333" stroke-width="1.6"%s%s/>'
                   % (x1, y1, x2, y2, dash, line_marker))
        if st['marker'] == 'arrow_x':
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                       'stroke="#B03030" stroke-width="1.6" '
                       'marker-end="url(#mk-arrow-x)"/>' % (x1, y1, x2, y2))
        label = r.get('label') or ('?' if r['type'] == 'unclear' else '')
        if label:
            edge_labels.append((r['id'], label, (x1 + x2) / 2.0,
                                (y1 + y2) / 2.0 - 5))
        out.append('</g>')
    out.append('</g>')

    out.append(layer_open('entities'))
    for e in m['entities']:
        x, y, w, h = boxes[e['id']]
        color = m['classes'][e['class']]['color']
        out.append('<g id="ent-%s" data-entity="%s" data-label="%s" '
                   'data-class="%s">'
                   % (esc(e['id']), esc(e['id']), esc(e['label']),
                      esc(e['class'])))
        out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="8" '
                   'fill="%s" fill-opacity="0.18" stroke="%s" '
                   'stroke-width="1.8"/>' % (x, y, w, h, color, color))
        out.append('<text x="%.1f" y="%.1f" text-anchor="middle" '
                   'font-family="%s" font-size="13" fill="#1A1A1A">%s</text>'
                   % (x + w / 2.0, y + h / 2.0 + 4.5, FONT, esc(e['label'])))
        out.append('</g>')
    out.append('</g>')

    out.append(layer_open('labels'))
    out.append('<text id="figure-title" data-label="title" x="%d" y="34" '
               'text-anchor="middle" font-family="%s" font-size="17" '
               'font-weight="bold" fill="#111111">%s</text>'
               % (cw // 2, FONT, esc(m['figure'].get('title', ''))))
    for rid, text, lx, ly in edge_labels:
        out.append('<text id="rel-%s-label" data-edge-label="%s" x="%.1f" '
                   'y="%.1f" text-anchor="middle" font-family="%s" '
                   'font-size="11" fill="#444444">%s</text>'
                   % (esc(rid), esc(rid), lx, ly, FONT, esc(text)))
    for a in m.get('annotations', []):
        gpos = a.get('grid') or {'col': 0, 'row': 0}
        ax = MARGIN_X + gpos['col'] * GRID_COL_W
        ay = MARGIN_Y + gpos['row'] * GRID_ROW_H + BOX_H + 18
        out.append('<text id="ann-%s" data-annotation="%s" x="%.1f" y="%.1f" '
                   'font-family="%s" font-size="11" font-style="italic" '
                   'fill="#555555">%s</text>'
                   % (esc(a['id']), esc(a['id']), ax, ay, FONT, esc(a['text'])))
    out.append('</g>')

    out.append(layer_open('legend'))
    lx, ly = MARGIN_X, ch - 96
    out.append('<g id="legend" data-legend="main">')
    out.append('<text id="legend-title" x="%.1f" y="%.1f" font-family="%s" '
               'font-size="12" font-weight="bold" fill="#333333">Legend</text>'
               % (lx, ly, FONT))
    cy = ly + 18
    for cname in used_classes:
        c = m['classes'][cname]
        out.append('<g id="legend-class-%s" data-legend-class="%s">'
                   % (esc(cname), esc(cname)))
        out.append('<rect x="%.1f" y="%.1f" width="14" height="14" rx="3" '
                   'fill="%s" fill-opacity="0.18" stroke="%s" '
                   'stroke-width="1.5"/>' % (lx, cy - 11, c['color'], c['color']))
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="11" '
                   'fill="#333333">%s</text>'
                   % (lx + 20, cy, FONT, esc(c.get('label', cname))))
        out.append('</g>')
        cy += 18
    cy = ly + 18
    lx2 = lx + 210
    for tname in used_types:
        st = REL_STYLE[tname]
        marker = {'arrow': 'mk-arrow', 'arrow_open': 'mk-arrow-open',
                  'tbar': 'mk-tbar', 'dot': 'mk-dot',
                  'arrow_x': 'mk-arrow-x'}[st['marker']]
        dash = ' stroke-dasharray="%s"' % st['dash'] if st['dash'] else ''
        out.append('<g id="legend-rel-%s" data-legend-rel="%s">'
                   % (esc(tname), esc(tname)))
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                   'stroke="#333333" stroke-width="1.6"%s '
                   'marker-end="url(#%s)"/>'
                   % (lx2, cy - 4, lx2 + 34, cy - 4, dash, marker))
        out.append('<text x="%.1f" y="%.1f" font-family="%s" font-size="11" '
                   'fill="#333333">%s</text>'
                   % (lx2 + 42, cy, FONT, esc(st['glyph'])))
        out.append('</g>')
        cy += 18
    out.append('</g>')
    out.append('</g>')

    out.append('</svg>')
    return '\n'.join(out) + '\n', warnings, (cw, ch)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--svg', required=True)
    ap.add_argument('--report', required=True)
    args = ap.parse_args()
    try:
        m = load_manifest(args.manifest)
    except ManifestError as exc:
        print('MANIFEST ERROR: %s' % exc, file=sys.stderr)
        sys.exit(1)
    svg, warnings, (cw, ch) = render(m)
    with open(args.svg, 'w', encoding='utf-8') as f:
        f.write(svg)
    report = {'status': 'ok',
              'svg': args.svg,
              'canvas': {'width': cw, 'height': ch},
              'entities': len(m['entities']),
              'relations': len(m.get('relations', [])),
              'groups': len(m.get('groups', [])),
              'layout_warnings': warnings,
              'generator': 'render_manifest.py v' + VERSION}
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    for w in warnings:
        print('LAYOUT WARNING: ' + w, file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
