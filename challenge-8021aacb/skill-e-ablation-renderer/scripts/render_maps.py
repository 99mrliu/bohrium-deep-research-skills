#!/usr/bin/env python3
"""render_maps.py -- 结构图渲染器 (纯文本 SVG + 自包含 HTML, 无二进制依赖)。

产物:
  structure_map.svg   章节流 + 论断/证据节点图 (SVG 为文本格式, 符合资源约束)
  report.html         自包含报告: 内嵌 SVG + 诊断表, 浏览器可直接打开;
                      运行时如有渲染工具可再转 PDF/PNG, 但不依赖。

用法:
    python3 render_maps.py GRAPH_JSON DIAGNOSIS_JSON OUT_DIR
DIAGNOSIS_JSON 可为 '-' 表示无诊断, 仅渲染结构图。
"""
import html
import json
import os
import sys

KIND_COLOR = {'section': '#2b6cb0', 'claim': '#c53030', 'evidence': '#2f855a'}
COLS = 4
CW, CH = 300, 96


def esc(s):
    return html.escape(str(s), quote=True)


def layout(graph):
    secs = [n for n in graph['nodes'] if n['kind'] == 'section']
    items = []
    for s in secs:
        items.append(s)
        items += [n for n in graph['nodes']
                  if n.get('section') == s['id'] and n['kind'] != 'section']
    pos = {}
    for i, n in enumerate(items):
        pos[n['id']] = (24 + (i % COLS) * (CW + 16), 24 + (i // COLS) * (CH + 28))
    rows = (len(items) + COLS - 1) // COLS or 1
    return pos, 24 * 2 + COLS * (CW + 16), 24 * 2 + rows * (CH + 28)


def svg(graph):
    pos, W, H = layout(graph)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'viewBox="0 0 %d %d" font-family="sans-serif" font-size="12">'
             % (W, H, W, H),
             '<defs><marker id="arr" markerWidth="8" markerHeight="8" refX="8" '
             'refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#888"/>'
             '</marker></defs>']
    orphan = set(graph['stats'].get('orphan_claims_visual', []))
    for e in graph['edges']:
        if e['rel'] != 'supports?':
            continue
        x1, y1 = pos[e['from']]
        x2, y2 = pos[e['to']]
        parts.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#888" '
                     'stroke-dasharray="4 3" marker-end="url(#arr)"/>'
                     % (x1 + CW / 2, y1 + CH / 2, x2 + CW / 2, y2 + CH / 2))
    for n in graph['nodes']:
        if n['id'] not in pos:
            continue
        x, y = pos[n['id']]
        color = KIND_COLOR[n['kind']]
        dash = ' stroke-dasharray="6 4"' if n['id'] in orphan else ''
        label = n.get('title') or n.get('text', '')
        tag = {'section': '节', 'claim': '论断', 'evidence': '证据'}[n['kind']]
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" rx="8" '
                     'fill="white" stroke="%s" stroke-width="2"%s/>'
                     % (x, y, CW, CH, color, dash))
        parts.append('<text x="%d" y="%d" fill="%s" font-weight="bold">[%s] %s</text>'
                     % (x + 8, y + 20, color, tag, esc(n['id'])))
        # 简单折行
        line1, line2 = label[:26], label[26:52]
        parts.append('<text x="%d" y="%d" fill="#333">%s</text>' % (x + 8, y + 42, esc(line1)))
        if line2:
            parts.append('<text x="%d" y="%d" fill="#333">%s…</text>' % (x + 8, y + 60, esc(line2)))
    parts.append('<text x="24" y="%d" fill="#666">虚线边框 = 可视化判定的孤立论断'
                 '（无就近证据），supports? 边为近似，需人工复核</text>' % (H - 8))
    parts.append('</svg>')
    return '\n'.join(parts)


def render(graph_path, diag_path, out_dir):
    with open(graph_path, encoding='utf-8') as f:
        graph = json.load(f)
    os.makedirs(out_dir, exist_ok=True)
    svg_text = svg(graph)
    with open(os.path.join(out_dir, 'structure_map.svg'), 'w', encoding='utf-8') as f:
        f.write(svg_text)

    diag_html = '<p>（未提供诊断 JSON，仅渲染结构图。）</p>'
    if diag_path != '-':
        with open(diag_path, encoding='utf-8') as f:
            diag = json.load(f)
        rows = []
        for x in diag.get('findings', []):
            rows.append('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                        % (esc(x.get('id', '')), esc(x.get('dimension', '')),
                           esc(x.get('location', x.get('anchor', ''))),
                           esc(x.get('defect_class', '')),
                           esc(x.get('severity', ''))))
        diag_html = ('<table border="1" cellspacing="0" cellpadding="6">'
                     '<tr><th>ID</th><th>维度</th><th>位置</th><th>缺陷子类</th>'
                     '<th>严重度</th></tr>%s</table>' % ''.join(rows))
    stats = graph['stats']
    page = ('<!doctype html><html lang="zh"><head><meta charset="utf-8">'
            '<title>结构诊断报告</title></head><body>'
            '<h1>论文结构诊断报告（可视化附件）</h1>'
            '<p>章节 %d · 论断 %d · 证据 %d · 可视化孤立论断 %d</p>'
            '%s<h2>诊断清单</h2>%s'
            '<hr><p style="color:#888">本 HTML 为文本格式自包含报告；'
            '如有渲染工具可另转 PDF/PNG 预览。</p></body></html>'
            % (stats['sections'], stats['claims'], stats['evidence'],
               len(stats.get('orphan_claims_visual', [])), svg_text, diag_html))
    with open(os.path.join(out_dir, 'report.html'), 'w', encoding='utf-8') as f:
        f.write(page)
    print(json.dumps({'svg_bytes': len(svg_text), 'html_bytes': len(page)},
                     ensure_ascii=False))


if __name__ == '__main__':
    if len(sys.argv) != 4:
        sys.exit('usage: render_maps.py GRAPH_JSON DIAGNOSIS_JSON|- OUT_DIR')
    render(*sys.argv[1:4])
