"""archetypes.py -- Bundle B (ga-archetype-forge): the visual-grammar library.

Five hand-tuned SVG skeleton builders for graphical abstracts. Pure stdlib:
each returns a complete SVG string with
  - one <g> per logical layer, labelled via inkscape:label + id
  - every <text> carrying data-max-w (max pixel width of its container) so
    canvas_audit.py can prove no overflow instead of eyeballing it
  - a <defs> arrowhead marker and the style tokens from style_tokens.md

Public API:
  ARCHETYPES = {"linear-pipeline": build_linear_pipeline, ...}
  build_*(params: dict) -> str (SVG)

All builders accept params["canvas"] = {"w": px, "h": px} (default 691x384,
i.e. 7.2 x 4.0 in at 96 px/in) and params["title"].
"""
import html
import json

TOKENS = {
    "ink": "#1a1a1a",
    "entity": "#56B4E9", "process": "#009E73", "outcome": "#E69F00",
    "condition": "#F0E442", "intervention": "#D55E00",
    "control": "#999999", "accent": "#0072B2", "purple": "#CC79A7",
    "panel_bg": "#FFFFFF", "band": "#F2F2F2",
}
ROLE_FILL = {"entity": "entity", "process": "process", "outcome": "outcome",
             "condition": "condition", "intervention": "intervention",
             "note": "panel_bg", "control": "control"}
FONT = "Helvetica, Arial, sans-serif"


def esc(s):
    return html.escape(str(s), quote=True)


def _header(w, h, title):
    return ('<svg xmlns="http://www.w3.org/2000/svg" '
            'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
            'width="%d" height="%d" viewBox="0 0 %d %d">\n'
            '<title>%s</title>\n'
            '<defs><marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>'
            '<marker id="barb" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="7" markerHeight="7" orient="auto">'
            '<path d="M9,1 L9,9" stroke="%s" stroke-width="2"/></marker>'
            '</defs>\n'
            '<rect id="background" x="0" y="0" width="%d" height="%d" '
            'fill="#ffffff"/>\n'
            % (w, h, w, h, esc(title or "graphical abstract"),
               TOKENS["ink"], TOKENS["ink"], w, h))


def _title_band(w, title, sub=""):
    if not title:
        return "", 0
    band = ('<g id="layer-title" inkscape:label="title">\n'
            '<text id="title" x="16" y="26" font-family="%s" font-size="17" '
            'font-weight="bold" fill="%s" data-max-w="%d">%s</text>\n'
            % (FONT, TOKENS["ink"], w - 32, esc(title)))
    if sub:
        band += ('<text id="subtitle" x="16" y="44" font-family="%s" '
                 'font-size="11" fill="#444444" data-max-w="%d">%s</text>\n'
                 % (FONT, w - 32, esc(sub)))
    return band + "</g>\n", 52 if sub else 36


def _text_lines(x, y, lines, size, fill, anchor="middle", max_w=0, bold=False,
                gid="text"):
    out = ['<text id="%s" x="%s" y="%s" font-family="%s" font-size="%s" '
           'fill="%s" text-anchor="%s"%s data-max-w="%d">'
           % (gid, x, y, FONT, size, fill, anchor,
              ' font-weight="bold"' if bold else "", max_w)]
    for i, ln in enumerate(lines):
        dy = 0 if i == 0 else size * 1.25
        out.append('<tspan x="%s" dy="%.1f">%s</tspan>' % (x, dy, esc(ln)))
    out.append('</text>\n')
    return "".join(out)


def _box(x, y, w, h, role=None, fill=None, gid="box", rx=8, stroke=None):
    fc = fill or TOKENS[ROLE_FILL.get(role or "note", "panel_bg")]
    sc = stroke or TOKENS["ink"]
    return ('<rect id="%s" x="%.1f" y="%.1f" width="%.1f" height="%.1f" rx="%d" '
            'fill="%s" stroke="%s" stroke-width="1.2"/>\n'
            % (gid, x, y, w, h, rx, fc, sc))


def _text_on(fill_hex):
    """Readable text colour for a given fill: white on dark fills."""
    h = (fill_hex or "#ffffff").lstrip("#")
    if len(h) != 6:
        return TOKENS["ink"]
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return TOKENS["ink"]
    def f(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    return "#ffffff" if lum < 0.25 else TOKENS["ink"]


def _est_w(text, size_px):
    w = 0.0
    for ch in str(text):
        if ch in "iljtfI.,;:'!|()[] ":
            w += 0.28
        elif ch in "mwMW@%&":
            w += 0.85
        else:
            w += 0.55
    return w * size_px


def _arrow(x1, y1, x2, y2, label=None, size=10, gid="arrow", dashed=False,
           inhibit=False):
    marker = "barb" if inhibit else "arrowhead"
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    out = ('<line id="%s" x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
           'stroke-width="1.6" marker-end="url(#%s)"%s/>\n'
           % (gid, x1, y1, x2, y2, TOKENS["ink"], marker, dash))
    if label:
        out += _text_lines((x1 + x2) / 2, min(y1, y2) - 5, [label], size,
                           "#333333", max_w=max(abs(x2 - x1) - 8,
                                                _est_w(label, size) + 4),
                           gid=gid + "-label")
    return out


def _legend(w, h, items):
    """items: [{color_token, label}] bottom strip."""
    if not items:
        return ""
    y = h - 14
    x = 16.0
    out = ['<g id="layer-legend" inkscape:label="legend">\n']
    for i, it in enumerate(items):
        out.append('<rect id="legend-swatch-%d" x="%.1f" y="%.1f" width="11" '
                   'height="11" fill="%s" stroke="%s" stroke-width="0.8"/>\n'
                   % (i, x, y - 10, TOKENS.get(it["color_token"], it["color_token"]),
                      TOKENS["ink"]))
        out.append('<text id="legend-label-%d" x="%.1f" y="%.1f" '
                   'font-family="%s" font-size="9" fill="#333333" '
                   'data-max-w="160">%s</text>\n'
                   % (i, x + 15, y, FONT, esc(it["label"])))
        x += 15 + 9 * 0.52 * len(it["label"]) + 24
    out.append("</g>\n")
    return "".join(out)


def _canvas(params):
    c = params.get("canvas", {})
    return int(c.get("w", 691)), int(c.get("h", 384))


# ---------------------------------------------------------------- archetype 1
def build_linear_pipeline(params):
    """stages: [{label:[lines], role, sublabel:[lines]}]; edges: [{label}]
    between consecutive stages; optional title/subtitle/legend."""
    w, h = _canvas(params)
    svg = _header(w, h, params.get("title"))
    band, top = _title_band(w, params.get("title"), params.get("subtitle"))
    svg += band
    stages = params.get("stages", [])
    edges = params.get("edges", [])
    n = max(len(stages), 1)
    margin, gap = 20.0, 34.0
    bw = (w - 2 * margin - (n - 1) * gap) / n
    bh = min(96.0, h - top - 90)
    y = top + (h - top - 40 - bh) / 2
    body = ['<g id="layer-pipeline" inkscape:label="pipeline">\n']
    centers = []
    for i, st in enumerate(stages):
        x = margin + i * (bw + gap)
        body.append(_box(x, y, bw, bh, role=st.get("role"),
                         fill=st.get("fill"), gid="stage-%d" % i))
        lines = st.get("label", [])
        if isinstance(lines, str):
            lines = [lines]
        sub = st.get("sublabel", [])
        if isinstance(sub, str):
            sub = [sub]
        n_lines = len(lines) + len(sub)
        ty = y + bh / 2 - (n_lines - 1) * 0.625 * 11
        body.append(_text_lines(x + bw / 2, ty, lines, 11, TOKENS["ink"],
                                max_w=bw - 10, bold=True,
                                gid="stage-%d-label" % i))
        if sub:
            body.append(_text_lines(x + bw / 2, ty + len(lines) * 13.75, sub,
                                    9, "#222222", max_w=bw - 10,
                                    gid="stage-%d-sub" % i))
        centers.append((x, y, bw, bh))
    for i in range(n - 1):
        lab = edges[i].get("label") if i < len(edges) else None
        x1 = centers[i][0] + bw
        x2 = centers[i + 1][0]
        body.append(_arrow(x1 + 3, y + bh / 2, x2 - 3, y + bh / 2, label=lab,
                           gid="edge-%d-%d" % (i, i + 1)))
    body.append("</g>\n")
    svg += "".join(body)
    svg += _legend(w, h, params.get("legend", []))
    return svg + "</svg>\n"


# ---------------------------------------------------------------- archetype 2
def build_hub_mechanism(params):
    """center: {label}; satellites: [{label, role, angle_deg, edge:'in'|'out',
    edge_label}]. Radial mechanism diagram."""
    import math
    w, h = _canvas(params)
    svg = _header(w, h, params.get("title"))
    band, top = _title_band(w, params.get("title"), params.get("subtitle"))
    svg += band
    cx, cy = w / 2, top + (h - top - 30) / 2
    r_hub = min(w, h - top) * 0.16
    bw, bh = 100.0, 40.0
    max_orbit = min(w / 2 - bw / 2 - 8, (h - top - 30) / 2 - bh / 2 - 8)
    need_orbit = r_hub + max(bw, bh) / 2 + 26
    r_orbit = min(max(need_orbit, 60.0), max(max_orbit, 60.0))
    if r_orbit < need_orbit:  # shrink hub before letting boxes collide
        r_hub = max(28.0, r_orbit - max(bw, bh) / 2 - 26)
    body = ['<g id="layer-mechanism" inkscape:label="mechanism">\n']
    body.append('<circle id="hub" cx="%.1f" cy="%.1f" r="%.1f" fill="%s" '
                'stroke="%s" stroke-width="1.4"/>\n'
                % (cx, cy, r_hub, TOKENS["accent"], TOKENS["ink"]))
    hub_label = params.get("center", {}).get("label", [])
    if isinstance(hub_label, str):
        hub_label = [hub_label]
    hub_size = 11.0
    usable = 2 * r_hub - 10
    longest = max((_est_w(ln, hub_size) for ln in hub_label), default=0)
    while longest > usable and hub_size > 8:
        hub_size -= 1
        longest = max((_est_w(ln, hub_size) for ln in hub_label), default=0)
    body.append(_text_lines(cx, cy - (len(hub_label) - 1) * 7, hub_label,
                            hub_size, "#ffffff", max_w=usable, bold=True,
                            gid="hub-label"))
    sats = params.get("satellites", [])
    for i, s in enumerate(sats):
        ang = math.radians(s.get("angle_deg", i * 360.0 / max(len(sats), 1)))
        sx, sy = cx + r_orbit * math.cos(ang), cy + r_orbit * math.sin(ang)
        body.append(_box(sx - bw / 2, sy - bh / 2, bw, bh, role=s.get("role"),
                         fill=s.get("fill"), gid="sat-%d" % i))
        lab = s.get("label", [])
        if isinstance(lab, str):
            lab = [lab]
        body.append(_text_lines(sx, sy - (len(lab) - 1) * 6 + 4, lab, 9,
                                TOKENS["ink"], max_w=bw - 10,
                                gid="sat-%d-label" % i))
        if s.get("edge", "in") == "in":
            x1, y1 = sx - math.copysign(bw / 2, math.cos(ang)), sy
            x2, y2 = cx + math.copysign(r_hub, math.cos(ang)), cy
        else:
            x1, y1 = cx + math.copysign(r_hub, math.cos(ang)), cy
            x2, y2 = sx - math.copysign(bw / 2, math.cos(ang)), sy
        body.append(_arrow(x1, y1, x2, y2, label=s.get("edge_label"),
                           gid="spoke-%d" % i,
                           inhibit=s.get("inhibit", False)))
    body.append("</g>\n")
    svg += "".join(body)
    svg += _legend(w, h, params.get("legend", []))
    return svg + "</svg>\n"


# ---------------------------------------------------------------- archetype 3
def build_compare_split(params):
    """left/right: {heading, items:[{label, role}], stats:[str]}; verdict."""
    w, h = _canvas(params)
    svg = _header(w, h, params.get("title"))
    band, top = _title_band(w, params.get("title"), params.get("subtitle"))
    svg += band
    colw = (w - 3 * 24) / 2
    body = ['<g id="layer-compare" inkscape:label="comparison">\n']
    for k, x in (("left", 24.0), ("right", 48.0 + colw)):
        col = params.get(k, {})
        body.append('<rect id="%s-panel" x="%.1f" y="%.1f" width="%.1f" '
                    'height="%.1f" fill="%s" stroke="#bbbbbb" '
                    'stroke-dasharray="4,3"/>\n'
                    % (k, x, top + 8, colw, h - top - 70, TOKENS["band"]))
        body.append(_text_lines(x + colw / 2, top + 34,
                                [col.get("heading", k)], 13, TOKENS["ink"],
                                max_w=colw - 16, bold=True,
                                gid=k + "-heading"))
        yy = top + 60.0
        for i, it in enumerate(col.get("items", [])):
            body.append(_box(x + 16, yy, colw - 32, 40, role=it.get("role"),
                             fill=it.get("fill"), gid="%s-item-%d" % (k, i)))
            lab = it.get("label", [])
            if isinstance(lab, str):
                lab = [lab]
            body.append(_text_lines(x + colw / 2, yy + 20 - (len(lab) - 1) * 6,
                                    lab, 10, TOKENS["ink"],
                                    max_w=colw - 48,
                                    gid="%s-item-%d-label" % (k, i)))
            yy += 52.0
        for st in col.get("stats", []):
            body.append(_text_lines(x + 20, yy + 8, [st], 10, "#222222",
                                    anchor="start", max_w=colw - 40,
                                    gid="%s-stat" % k))
            yy += 18.0
    body.append(_arrow(24 + colw + 2, top + (h - top) / 2,
                       48 + colw - 2, top + (h - top) / 2,
                       label=params.get("transition"), gid="transition"))
    if params.get("verdict"):
        body.append(_text_lines(w / 2, h - 34, [params["verdict"]], 12,
                                TOKENS["accent"], max_w=w - 48, bold=True,
                                gid="verdict"))
    body.append("</g>\n")
    svg += "".join(body)
    return svg + "</svg>\n"


# ---------------------------------------------------------------- archetype 4
def build_layered_stack(params):
    """layers: [{label, role, fill, thickness}]; side annotations with leaders.
    For device stacks / tissue strata / membrane systems."""
    w, h = _canvas(params)
    svg = _header(w, h, params.get("title"))
    band, top = _title_band(w, params.get("title"), params.get("subtitle"))
    svg += band
    layers = params.get("layers", [])
    x0, x1 = 60.0, w * 0.62
    total_frac = sum(l.get("thickness", 1.0) for l in layers) or 1.0
    avail = h - top - 70
    body = ['<g id="layer-stack" inkscape:label="stack">\n']
    y = top + 20.0
    for i, l in enumerate(layers):
        lh = avail * l.get("thickness", 1.0) / total_frac
        body.append('<rect id="stratum-%d" x="%.1f" y="%.1f" width="%.1f" '
                    'height="%.1f" fill="%s" stroke="%s" stroke-width="1"/>\n'
                    % (i, x0, y, x1 - x0, lh,
                       TOKENS.get(l.get("fill") or ROLE_FILL.get(
                           l.get("role", "note"), "panel_bg"), l.get("fill")),
                       TOKENS["ink"]))
        lab = l.get("label", [])
        if isinstance(lab, str):
            lab = [lab]
        fill_hex = TOKENS.get(l.get("fill") or ROLE_FILL.get(
            l.get("role", "note"), "panel_bg"), l.get("fill"))
        body.append(_text_lines((x0 + x1) / 2, y + lh / 2 + 4, lab, 10,
                                _text_on(fill_hex), max_w=x1 - x0 - 14,
                                gid="stratum-%d-label" % i))
        note = l.get("note")
        if note:
            nx = x1 + 40
            body.append('<line id="leader-%d" x1="%.1f" y1="%.1f" x2="%.1f" '
                        'y2="%.1f" stroke="#888888" stroke-width="0.8"/>\n'
                        % (i, x1 + 2, y + lh / 2, nx - 6, y + lh / 2))
            body.append(_text_lines(nx, y + lh / 2 + 4, [note], 9, "#333333",
                                    anchor="start", max_w=w - nx - 16,
                                    gid="note-%d" % i))
        y += lh
    if params.get("scale_bar"):
        sb = params["scale_bar"]
        body.append('<line id="scale-bar" x1="%.1f" y1="%.1f" x2="%.1f" '
                    'y2="%.1f" stroke="%s" stroke-width="2"/>\n'
                    % (x0, h - 44, x0 + sb.get("px", 60), h - 44, TOKENS["ink"]))
        body.append(_text_lines(x0, h - 50, [sb.get("label", "")], 9,
                                "#333333", anchor="start", max_w=140,
                                gid="scale-label"))
    body.append("</g>\n")
    svg += "".join(body)
    svg += _legend(w, h, params.get("legend", []))
    return svg + "</svg>\n"


# ---------------------------------------------------------------- archetype 5
def build_data_panel(params):
    """charts: [{kind:'bar'|'line', title, x_labels, y_label, series:
    [{name, values, color_token}]}] arranged in a row; stdlib-only plotting."""
    w, h = _canvas(params)
    svg = _header(w, h, params.get("title"))
    band, top = _title_band(w, params.get("title"), params.get("subtitle"))
    svg += band
    charts = params.get("charts", [])
    n = max(len(charts), 1)
    cw = (w - 32 - (n - 1) * 28) / n
    body = ['<g id="layer-data" inkscape:label="data-panels">\n']
    for ci, ch in enumerate(charts):
        ox = 16 + ci * (cw + 28)
        oy, chh = top + 26, h - top - 96
        pad_l, pad_b = 44.0, 30.0
        body.append(_text_lines(ox + cw / 2, top + 12, [ch.get("title", "")],
                                11, TOKENS["ink"], max_w=cw - 8, bold=True,
                                gid="chart-%d-title" % ci))
        series = ch.get("series", [])
        vmax = max([max(s.get("values", [0]) or [0]) for s in series] + [1e-9])
        vmax *= 1.1
        pw, ph = cw - pad_l - 8, chh - pad_b
        body.append('<line id="chart-%d-yaxis" x1="%.1f" y1="%.1f" x2="%.1f" '
                    'y2="%.1f" stroke="%s" stroke-width="1"/>\n'
                    % (ci, ox + pad_l, oy, ox + pad_l, oy + ph, TOKENS["ink"]))
        body.append('<line id="chart-%d-xaxis" x1="%.1f" y1="%.1f" x2="%.1f" '
                    'y2="%.1f" stroke="%s" stroke-width="1"/>\n'
                    % (ci, ox + pad_l, oy + ph, ox + pad_l + pw, oy + ph,
                       TOKENS["ink"]))
        for tv in (0, 0.5, 1.0):
            val = vmax * tv
            yy = oy + ph - ph * tv
            body.append('<text id="chart-%d-tick" x="%.1f" y="%.1f" '
                        'font-family="%s" font-size="8" fill="#555555" '
                        'text-anchor="end" data-max-w="38">%s</text>\n'
                        % (ci, ox + pad_l - 4, yy + 3, FONT,
                           esc(_fmt(val))))
        if ch.get("y_label"):
            body.append('<text id="chart-%d-ylabel" x="%.1f" y="%.1f" '
                        'font-family="%s" font-size="9" fill="#333333" '
                        'text-anchor="middle" transform="rotate(-90 %.1f %.1f)" '
                        'data-max-w="%d">%s</text>\n'
                        % (ci, ox + 12, oy + ph / 2, FONT, ox + 12,
                           oy + ph / 2, int(ph), esc(ch["y_label"])))
        nser = max(len(series), 1)
        for si, s in enumerate(series):
            vals = s.get("values", [])
            m = max(len(vals), 1)
            col = TOKENS.get(s.get("color_token", "accent"),
                             s.get("color_token", TOKENS["accent"]))
            if ch.get("kind", "bar") == "bar":
                slot = pw / m
                bw2 = slot * 0.7 / nser
                for vi, v in enumerate(vals):
                    bh2 = ph * v / vmax
                    bx = ox + pad_l + vi * slot + slot * 0.15 + si * bw2
                    body.append('<rect id="chart-%d-bar-%d-%d" x="%.1f" '
                                'y="%.1f" width="%.1f" height="%.1f" '
                                'fill="%s"/>\n'
                                % (ci, si, vi, bx, oy + ph - bh2, bw2 * 0.92,
                                   bh2, col))
            else:
                pts = " ".join("%.1f,%.1f"
                               % (ox + pad_l + pw * vi / max(m - 1, 1),
                                  oy + ph - ph * v / vmax)
                               for vi, v in enumerate(vals))
                body.append('<polyline id="chart-%d-line-%d" points="%s" '
                            'fill="none" stroke="%s" stroke-width="1.6"/>\n'
                            % (ci, si, pts, col))
        labels = ch.get("x_labels", [])
        for li, lab in enumerate(labels):
            body.append('<text id="chart-%d-xlab-%d" x="%.1f" y="%.1f" '
                        'font-family="%s" font-size="8" fill="#555555" '
                        'text-anchor="middle" data-max-w="%.0f">%s</text>\n'
                        % (ci, li, ox + pad_l + pw * (li + 0.5) / max(len(labels), 1),
                           oy + ph + 12, FONT,
                           pw / max(len(labels), 1) - 4, esc(lab)))
    body.append("</g>\n")
    svg += "".join(body)
    legend_items = [{"color_token": s.get("color_token", "accent"),
                     "label": s.get("name", "")}
                    for ch in charts for s in ch.get("series", [])
                    if s.get("name")]
    svg += _legend(w, h, legend_items if len(legend_items) > 1 else [])
    return svg + "</svg>\n"


def _fmt(v):
    return ("%g" % v)


ARCHETYPES = {
    "linear-pipeline": build_linear_pipeline,
    "hub-mechanism": build_hub_mechanism,
    "compare-split": build_compare_split,
    "layered-stack": build_layered_stack,
    "data-panel": build_data_panel,
}

if __name__ == "__main__":
    import sys
    params = json.loads(open(sys.argv[2]).read()) if len(sys.argv) > 2 else {}
    print(ARCHETYPES[sys.argv[1]](params))
