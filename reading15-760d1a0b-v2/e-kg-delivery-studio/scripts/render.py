#!/usr/bin/env python3
"""render.py - stdlib-only deterministic rendering layer (signature of bundle E).

Turns a verified graph (<work>/graph.json) plus executed queries
(<work>/queries.json) into a complete, human-inspectable deliverable set:

  graph.svg          full-graph deterministic layered-layout SVG (no graphviz)
  query_<id>.svg     one SVG per executed query, result subgraph highlighted
  report.html        self-contained report: inline SVG + query tables +
                     evidence index with verbatim quotes
  report.md          markdown summary
  nodes.csv / edges.csv
  graph.jsonld       JSON-LD export
  graph.graphml      GraphML export
  evidence_index.json  every quote, re-verified against the corpus
  verification_report.json  copy of the mechanical verifier's report

Layout algorithm (deterministic, documented in references/artifact-guide.md):
  * one column per entity type, in a fixed canonical TYPE_ORDER;
  * nodes sorted within a column by (label.casefold(), id);
  * x = column index, y = cumulative top-aligned stack;
  * edges are cubic bezier curves clipped to node-box borders, bowed right
    for same-column edges; arrow markers; relation label at bezier midpoint
    on a white chip;
  * query SVGs reuse the IDENTICAL layout of the full graph and only change
    opacity/emphasis, so coordinates are directly comparable across files.

Everything is pure Python 3 stdlib (xml/html escaping via stdlib only).
No wall-clock timestamps are written into any artifact.
"""

import argparse
import csv
import json
import os
import sys
from html import escape as hesc
from xml.sax.saxutils import escape as xesc

SCHEMA_VERSION = "e-kg-delivery-studio/1.0"

# Canonical layer order (left -> right). Chosen once, documented, and fixed so
# that output is deterministic; it also points most relation directions
# (claim->sample->method/material, method->metric, claim->condition) forward.
TYPE_ORDER = ["researcher", "task", "dataset", "claim", "sample", "method",
              "material", "metric", "condition", "note"]

PALETTE = {
    "researcher": ("#fbe9e7", "#d84315"),
    "task": ("#f1f8e9", "#558b2f"),
    "dataset": ("#ede7f6", "#5e35b1"),
    "claim": ("#fff3e0", "#e65100"),
    "sample": ("#e3f2fd", "#1565c0"),
    "method": ("#e8f5e9", "#2e7d32"),
    "material": ("#f3e5f5", "#6a1b9a"),
    "metric": ("#fffde7", "#f9a825"),
    "condition": ("#e0f7fa", "#00838f"),
    "note": ("#eceff1", "#546e7a"),
}
DEFAULT_COLOR = ("#eceff1", "#546e7a")

MARGIN_X = 40
MARGIN_TOP = 64
MARGIN_BOTTOM = 44
COL_W = 270
NODE_MIN_W = 96
NODE_MAX_W = 232
CHAR_W = 7.4
LINE_H = 15
NODE_PAD_V = 9
V_GAP = 34
MAX_LABEL_CHARS = 26
MAX_LABEL_LINES = 2

EDGE_COLOR = "#7a7a7a"
HILITE = "#d62728"
DIM_OPACITY = "0.12"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def fnum(v):
    """Deterministic compact number formatting."""
    s = "%.1f" % v
    return s[:-2] if s.endswith(".0") else s


def wrap_label(label, max_chars=MAX_LABEL_CHARS, max_lines=MAX_LABEL_LINES):
    """Greedy word wrap; if more than max_lines result, fold the remainder
    into the last line and truncate it with an ellipsis."""
    words = label.split()
    lines, cur = [], ""
    for w in words:
        while len(w) > max_chars:  # hard-split very long words
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(w[:max_chars])
            w = w[max_chars:]
        trial = (cur + " " + w).strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if not lines:
        lines = [""]
    if len(lines) > max_lines:
        last = " ".join(lines[max_lines - 1:])
        lines = lines[:max_lines]
        lines[-1] = (last[: max_chars - 1] + "…") if len(last) > max_chars \
            else last + " …"
    return lines


def node_box(lines):
    w = max(NODE_MIN_W, min(NODE_MAX_W, int(max(len(l) for l in lines) * CHAR_W) + 22))
    h = NODE_PAD_V * 2 + LINE_H * len(lines)
    return w, h


# ---------------------------------------------------------------------------
# deterministic layered layout
# ---------------------------------------------------------------------------

def compute_layout(graph):
    """Return (pos, layers, width, height); pos[id] = (x, y, w, h, lines)."""
    by_type = {}
    for n in graph["nodes"]:
        by_type.setdefault(n["type"], []).append(n)
    ordered_types = [t for t in TYPE_ORDER if t in by_type]
    ordered_types += sorted(t for t in by_type if t not in TYPE_ORDER)
    layers = []
    for t in ordered_types:
        col = sorted(by_type[t], key=lambda n: (n["label"].casefold(), n["id"]))
        layers.append((t, col))

    pos = {}
    max_col_h = 0
    for li, (t, col) in enumerate(layers):
        x = MARGIN_X + li * COL_W
        y = MARGIN_TOP
        for n in col:
            lines = wrap_label(n["label"])
            w, h = node_box(lines)
            pos[n["id"]] = (x, y, w, h, lines)
            y += h + V_GAP
        max_col_h = max(max_col_h, y - V_GAP)
    width = MARGIN_X * 2 + max(0, len(layers) - 1) * COL_W + NODE_MAX_W + 30
    height = max_col_h + MARGIN_BOTTOM
    return pos, layers, width, height


def _clip_to_border(x, y, w, h, tx, ty):
    """Intersect the segment from box center toward (tx,ty) with the box."""
    cx, cy = x + w / 2.0, y + h / 2.0
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    t = min((w / 2.0) / abs(dx) if dx else float("inf"),
            (h / 2.0) / abs(dy) if dy else float("inf"))
    return cx + dx * t, cy + dy * t


def _edge_geometry(e, pos):
    sx, sy, sw, sh, _ = pos[e["source"]]
    tx, ty, tw, th, _ = pos[e["target"]]
    scx, scy = sx + sw / 2.0, sy + sh / 2.0
    tcx, tcy = tx + tw / 2.0, ty + th / 2.0
    x1, y1 = _clip_to_border(sx, sy, sw, sh, tcx, tcy)
    x2, y2 = _clip_to_border(tx, ty, tw, th, scx, scy)
    if sx == tx:  # same layer column: bow out to the right
        off = 90.0
        c1 = (max(x1, x2) + off, y1)
        c2 = (max(x1, x2) + off, y2)
    else:
        sign = 1.0 if tcx > scx else -1.0
        hx = max(30.0, abs(tcx - scx) * 0.45)
        c1 = (x1 + sign * hx, y1)
        c2 = (x2 - sign * hx, y2)
    mx = (x1 + 3 * c1[0] + 3 * c2[0] + x2) / 8.0
    my = (y1 + 3 * c1[1] + 3 * c2[1] + y2) / 8.0
    return (x1, y1, c1, c2, x2, y2, mx, my)


# ---------------------------------------------------------------------------
# SVG rendering
# ---------------------------------------------------------------------------

def render_svg(graph, title, subtitle, highlight_nodes=None, highlight_edges=None):
    pos, layers, width, height = compute_layout(graph)
    hn = set(highlight_nodes or [])
    he = set(highlight_edges or [])
    highlighting = bool(hn or he)
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}

    parts = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append('<svg xmlns="http://www.w3.org/2000/svg" width="%s" height="%s" '
                 'viewBox="0 0 %s %s" font-family="Helvetica,Arial,sans-serif">'
                 % (fnum(width), fnum(height), fnum(width), fnum(height)))
    parts.append('<title>%s</title>' % xesc(title))
    parts.append('<defs>'
                 '<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" '
                 'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                 '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>'
                 '<marker id="arrH" viewBox="0 0 10 10" refX="9" refY="5" '
                 'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                 '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>'
                 '</defs>' % (EDGE_COLOR, HILITE))
    parts.append('<rect x="0" y="0" width="%s" height="%s" fill="#ffffff"/>'
                 % (fnum(width), fnum(height)))
    parts.append('<text x="%s" y="22" font-size="15" font-weight="bold" '
                 'fill="#222">%s</text>' % (fnum(MARGIN_X), xesc(title)))
    parts.append('<text x="%s" y="40" font-size="11" fill="#666">%s</text>'
                 % (fnum(MARGIN_X), xesc(subtitle)))

    # column captions
    for li, (t, col) in enumerate(layers):
        cx = MARGIN_X + li * COL_W + NODE_MAX_W / 2.0
        parts.append('<text x="%s" y="%s" font-size="11" font-weight="bold" '
                     'fill="%s" text-anchor="middle">%s (%d)</text>'
                     % (fnum(cx), fnum(MARGIN_TOP - 14),
                        PALETTE.get(t, DEFAULT_COLOR)[1], xesc(t), len(col)))

    # ---- edges (dim first, highlighted last so they sit on top) ----
    edges_sorted = sorted(graph["edges"], key=lambda e: e["id"])
    if highlighting:
        edges_sorted.sort(key=lambda e: e["id"] in he)
    for e in edges_sorted:
        x1, y1, c1, c2, x2, y2, mx, my = _edge_geometry(e, pos)
        hot = e["id"] in he
        dim = highlighting and not hot
        color = HILITE if hot else EDGE_COLOR
        sw = "2.4" if hot else "1.3"
        marker = "arrH" if hot else "arr"
        qual = e.get("qualifiers") or {}
        tip = e["id"] + " | " + e["relation"]
        if qual:
            tip += " | " + "; ".join("%s=%s" % (k, qual[k]) for k in sorted(qual))
        g_open = '<g opacity="%s">' % DIM_OPACITY if dim else "<g>"
        parts.append(g_open)
        parts.append('<title>%s</title>' % xesc(tip))
        parts.append('<path d="M%s,%s C%s,%s %s,%s %s,%s" fill="none" '
                     'stroke="%s" stroke-width="%s" marker-end="url(#%s)"/>'
                     % (fnum(x1), fnum(y1), fnum(c1[0]), fnum(c1[1]),
                        fnum(c2[0]), fnum(c2[1]), fnum(x2), fnum(y2),
                        color, sw, marker))
        label = e["relation"]
        lw = int(len(label) * 6.4) + 10
        parts.append('<rect x="%s" y="%s" width="%s" height="14" rx="4" '
                     'fill="#ffffff" stroke="%s" stroke-width="0.7" opacity="0.95"/>'
                     % (fnum(mx - lw / 2.0), fnum(my - 7), lw, color))
        parts.append('<text x="%s" y="%s" font-size="10" fill="%s" '
                     'text-anchor="middle">%s</text>'
                     % (fnum(mx), fnum(my + 3.5), color, xesc(label)))
        parts.append("</g>")

    # ---- nodes (dim first, highlighted last) ----
    node_ids = [n["id"] for t, col in layers for n in col]
    if highlighting:
        node_ids.sort(key=lambda i: i in hn)
    for nid in node_ids:
        n = nodes_by_id[nid]
        x, y, w, h, lines = pos[nid]
        hot = nid in hn
        dim = highlighting and not hot
        fill, stroke = PALETTE.get(n["type"], DEFAULT_COLOR)
        if hot:
            stroke = HILITE
        sw = "2.6" if hot else "1.2"
        g_open = '<g opacity="%s">' % DIM_OPACITY if dim else "<g>"
        parts.append(g_open)
        parts.append("<title>%s | %s | %s</title>"
                     % (xesc(n["id"]), xesc(n["type"]), xesc(n["label"])))
        parts.append('<rect x="%s" y="%s" width="%s" height="%s" rx="7" '
                     'fill="%s" stroke="%s" stroke-width="%s"/>'
                     % (fnum(x), fnum(y), fnum(w), fnum(h), fill, stroke, sw))
        cy = y + h / 2.0
        first_baseline = cy - (len(lines) - 1) * LINE_H / 2.0 + 4
        for i, line in enumerate(lines):
            parts.append('<text x="%s" y="%s" font-size="12" fill="#1a1a1a" '
                         'text-anchor="middle">%s</text>'
                         % (fnum(x + w / 2.0), fnum(first_baseline + i * LINE_H),
                            xesc(line)))
        parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# tabular / export writers
# ---------------------------------------------------------------------------

def _ev_ref(ev):
    return "%s:%s" % (ev["source_id"], ev["paragraph_id"])


def build_evidence_index(graph, corpus):
    """One entry per (item, evidence); each quote mechanically re-verified."""
    para_text = {}
    for src in corpus["sources"]:
        for p in src["paragraphs"]:
            para_text[(src["source_id"], p["paragraph_id"])] = p["text"]
    entries = []
    items = ([("node", n["id"], n["label"], n["evidence"]) for n in graph["nodes"]] +
             [("edge", e["id"], "%s %s %s" % (e["source"], e["relation"], e["target"]),
               e["evidence"]) for e in graph["edges"]])
    items.sort(key=lambda x: (x[0], x[1]))
    n_verified = 0
    for kind, iid, ilabel, evs in items:
        for ev in evs:
            text = para_text.get((ev["source_id"], ev["paragraph_id"]), "")
            ok = bool(ev["quote"]) and ev["quote"] in text
            n_verified += 1 if ok else 0
            entries.append({
                "evidence_id": "EV%03d" % (len(entries) + 1),
                "item_kind": kind, "item_id": iid, "item_label": ilabel,
                "source_id": ev["source_id"], "paragraph_id": ev["paragraph_id"],
                "section": ev.get("section", ""), "quote": ev["quote"],
                "quote_verified": ok,
            })
    return {"schema": SCHEMA_VERSION, "evidence": entries,
            "stats": {"entries": len(entries), "quote_verified": n_verified,
                      "quote_failed": len(entries) - n_verified}}


def write_csvs(graph, out_dir):
    with open(os.path.join(out_dir, "nodes.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["node_id", "type", "label", "aliases", "qualifiers",
                    "merged_from", "evidence_refs"])
        for n in graph["nodes"]:
            w.writerow([n["id"], n["type"], n["label"], "|".join(n["aliases"]),
                        json.dumps(n["qualifiers"], ensure_ascii=False,
                                   sort_keys=True),
                        "|".join(n["merged_from"]),
                        ";".join(_ev_ref(e) for e in n["evidence"])])
    labels = {n["id"]: n["label"] for n in graph["nodes"]}
    with open(os.path.join(out_dir, "edges.csv"), "w", encoding="utf-8",
              newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["edge_id", "relation", "source_id", "source_label",
                    "target_id", "target_label", "qualifiers", "evidence_refs"])
        for e in graph["edges"]:
            w.writerow([e["id"], e["relation"], e["source"],
                        labels.get(e["source"], "?"), e["target"],
                        labels.get(e["target"], "?"),
                        json.dumps(e["qualifiers"], ensure_ascii=False,
                                   sort_keys=True),
                        ";".join(_ev_ref(x) for x in e["evidence"])])


def write_jsonld(graph, out_dir):
    ctx = {
        "@vocab": "https://example.org/synthetic-kg#",
        "label": "http://www.w3.org/2000/01/rdf-schema#label",
        "source_id": "https://example.org/synthetic-kg#source_id",
        "paragraph_id": "https://example.org/synthetic-kg#paragraph_id",
        "quote": "https://example.org/synthetic-kg#verbatimQuote",
    }
    entries = []
    for n in graph["nodes"]:
        entries.append({
            "@id": "node/" + n["id"], "@type": ["Node", n["type"]],
            "label": n["label"], "aliases": n["aliases"],
            "merged_from": n["merged_from"],
            "evidence": [{"source_id": e["source_id"],
                          "paragraph_id": e["paragraph_id"],
                          "quote": e["quote"]} for e in n["evidence"]],
        })
    for e in graph["edges"]:
        entries.append({
            "@id": "edge/" + e["id"], "@type": ["Edge", e["relation"]],
            "relation": e["relation"],
            "source": {"@id": "node/" + e["source"]},
            "target": {"@id": "node/" + e["target"]},
            "qualifiers": e["qualifiers"],
            "evidence": [{"source_id": x["source_id"],
                          "paragraph_id": x["paragraph_id"],
                          "quote": x["quote"]} for x in e["evidence"]],
        })
    doc = {"@context": ctx, "@id": "graph/" + graph["case_id"],
           "synthetic": graph["synthetic"], "@graph": entries}
    with open(os.path.join(out_dir, "graph.jsonld"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def write_graphml(graph, out_dir):
    p = ['<?xml version="1.0" encoding="UTF-8"?>',
         '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
         '  <key id="n_type" for="node" attr.name="type" attr.type="string"/>',
         '  <key id="n_label" for="node" attr.name="label" attr.type="string"/>',
         '  <key id="n_ev" for="node" attr.name="evidence" attr.type="string"/>',
         '  <key id="e_rel" for="edge" attr.name="relation" attr.type="string"/>',
         '  <key id="e_qual" for="edge" attr.name="qualifiers" attr.type="string"/>',
         '  <key id="e_ev" for="edge" attr.name="evidence" attr.type="string"/>',
         '  <graph id="KG" edgedefault="directed">']
    for n in graph["nodes"]:
        p.append('    <node id="%s">' % xesc(n["id"]))
        p.append('      <data key="n_type">%s</data>' % xesc(n["type"]))
        p.append('      <data key="n_label">%s</data>' % xesc(n["label"]))
        p.append('      <data key="n_ev">%s</data>'
                 % xesc(";".join(_ev_ref(e) for e in n["evidence"])))
        p.append('    </node>')
    for e in graph["edges"]:
        p.append('    <edge id="%s" source="%s" target="%s">'
                 % (xesc(e["id"]), xesc(e["source"]), xesc(e["target"])))
        p.append('      <data key="e_rel">%s</data>' % xesc(e["relation"]))
        p.append('      <data key="e_qual">%s</data>'
                 % xesc(json.dumps(e["qualifiers"], ensure_ascii=False,
                                   sort_keys=True)))
        p.append('      <data key="e_ev">%s</data>'
                 % xesc(";".join(_ev_ref(x) for x in e["evidence"])))
        p.append('    </edge>')
    p.append('  </graph>')
    p.append('</graphml>')
    with open(os.path.join(out_dir, "graph.graphml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(p) + "\n")


# ---------------------------------------------------------------------------
# report.html / report.md
# ---------------------------------------------------------------------------

def _inline_svg(svg_text):
    lines = svg_text.splitlines()
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    return "\n".join(lines)


def _html_table(headers, rows):
    out = ["<table><thead><tr>"]
    out += ["<th>%s</th>" % hesc(h) for h in headers]
    out.append("</tr></thead><tbody>")
    for r in rows:
        out.append("<tr>" + "".join("<td>%s</td>" % hesc(str(c)) for c in r)
                   + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)


def build_html(graph, queries, evidence_index, verified, svgs, query_svgs):
    nodes = {n["id"]: n for n in graph["nodes"]}
    banner = ('<p class="syn">⚠ SYNTHETIC example output — demonstrates the '
              'deliverable set only; NOT a real-paper answer.</p>'
              if graph["synthetic"] else "")
    css = ("body{font-family:Helvetica,Arial,sans-serif;margin:24px;color:#1a1a1a}"
           "h1{font-size:22px}h2{font-size:17px;border-bottom:2px solid #ddd;"
           "padding-bottom:4px;margin-top:32px}h3{font-size:14px}"
           "table{border-collapse:collapse;margin:10px 0;font-size:12px}"
           "th,td{border:1px solid #bbb;padding:4px 8px;text-align:left;"
           "vertical-align:top}th{background:#f0f0f0}"
           "code{background:#f5f5f5;padding:1px 4px}"
           "blockquote{margin:4px 0;padding:4px 10px;border-left:3px solid "
           "#90caf9;background:#f7fbff;font-size:12px}"
           ".syn{background:#fff3cd;border:1px solid #ffc107;padding:8px;"
           "font-weight:bold}.meta{color:#555;font-size:12px}"
           "svg{max-width:100%;height:auto;border:1px solid #e0e0e0}")
    parts = ["<!DOCTYPE html>", '<html lang="zh"><head>',
             '<meta charset="utf-8">',
             "<title>KG delivery report - %s</title>" % hesc(graph["case_id"]),
             "<style>%s</style></head><body>" % css,
             "<h1>Knowledge-graph delivery report — <code>%s</code></h1>"
             % hesc(graph["case_id"]), banner,
             '<p class="meta">produced by %s · pure Python stdlib · deterministic '
             "layered layout (no graphviz) · %d nodes / %d edges / %d merges / "
             "%d non-merges / %d preserved conflicts</p>"
             % (SCHEMA_VERSION, graph["stats"]["nodes"], graph["stats"]["edges"],
                graph["stats"]["merges"], graph["stats"]["nonmerges"],
                graph["stats"]["conflicts"])]

    # 1. full graph
    parts.append("<h2>1. Full graph (graph.svg)</h2>")
    parts.append(_inline_svg(svgs["graph.svg"]))

    # 2. queries
    parts.append("<h2>2. Executed queries</h2>")
    for i, q in enumerate(queries["queries"], 1):
        parts.append("<h3>2.%d %s — <code>%s</code> (%s)</h3>"
                     % (i, hesc(q["id"]), hesc(q["type"]), hesc(q["status"])))
        if q.get("description"):
            parts.append("<p>%s</p>" % hesc(q["description"]))
        parts.append("<p>params: <code>%s</code></p>"
                     % hesc(json.dumps(q["params"], ensure_ascii=False,
                                       sort_keys=True)))
        svg_name = "query_%s.svg" % q["id"]
        if svg_name in query_svgs:
            parts.append(_inline_svg(query_svgs[svg_name]))
        if q["messages"]:
            parts.append("<ul>" + "".join("<li>%s</li>" % hesc(m)
                                          for m in q["messages"]) + "</ul>")
        if q["paths"]:
            parts.append("<p>paths found:</p><ol>" + "".join(
                "<li>%s</li>" % hesc(" → ".join(p["nodes"]))
                for p in q["paths"]) + "</ol>")
        if q["conflict_check"]:
            rows = [[c["metric_label"], ", ".join(c["distinct_values"]),
                     "; ".join("%s=%s (%s)" % (m["claim_id"], m["value"],
                                               ",".join(m["conditions"]) or "no condition")
                               for m in c["claims"]),
                     c["resolution"]] for c in q["conflict_check"]]
            parts.append("<p>conflict check (preserved, never merged):</p>")
            parts.append(_html_table(["metric", "distinct values", "claims",
                                      "resolution"], rows))
        erows = []
        for eid in q["edges"]:
            e = next(x for x in graph["edges"] if x["id"] == eid)
            erows.append([e["id"], e["relation"],
                          "%s (%s)" % (nodes[e["source"]]["label"], e["source"]),
                          "%s (%s)" % (nodes[e["target"]]["label"], e["target"]),
                          json.dumps(e["qualifiers"], ensure_ascii=False,
                                     sort_keys=True)])
        if erows:
            parts.append(_html_table(["edge", "relation", "source", "target",
                                      "qualifiers"], erows))
        if q["undetermined"]:
            parts.append("<p>undetermined / unknown (explicit):</p><ul>"
                         + "".join("<li><b>%s</b> — %s</li>"
                                   % (hesc(u["item"]), hesc(u["reason"]))
                                   for u in q["undetermined"]) + "</ul>")

    # 3. evidence index
    parts.append("<h2>3. Evidence index (verbatim quotes, re-verified)</h2>")
    rows = [[e["evidence_id"], e["item_kind"], e["item_id"], e["source_id"],
             e["paragraph_id"], e["section"], "“" + e["quote"] + "”",
             "✔" if e["quote_verified"] else "✘"]
            for e in evidence_index["evidence"]]
    parts.append(_html_table(["evidence_id", "kind", "item", "source",
                              "paragraph", "section", "verbatim quote",
                              "substring verified"], rows))

    # 4. merge / non-merge / conflicts / unreported
    parts.append("<h2>4. Merge ledger, non-merge registry, conflicts, unreported</h2>")
    if graph["merges"]:
        parts.append("<h3>4.1 merge ledger (justified cross-paper merges)</h3>")
        parts.append(_html_table(
            ["keep", "drop", "normalized key", "reason", "evidence"],
            [[m["keep"], m["drop"], m["key"], m["reason"],
              ";".join(_ev_ref(e) for e in m["evidence"])]
             for m in graph["merges"]]))
    if graph["nonmerges"]:
        parts.append("<h3>4.2 non-merge registry (same-name-different-object)</h3>")
        parts.append(_html_table(
            ["node a", "node b", "normalized key", "reason", "evidence"],
            [[x["a"], x["b"], x["normalized_key"], x["reason"],
              ";".join(_ev_ref(e) for e in x["evidence"])]
             for x in graph["nonmerges"]]))
    if graph["conflicts"]:
        parts.append("<h3>4.3 preserved numeric conflicts</h3>")
        parts.append(_html_table(
            ["metric", "distinct values", "claims (value @ conditions)",
             "resolution"],
            [[c["metric_label"], ", ".join(c["distinct_values"]),
              "; ".join("%s=%s (%s)" % (m["claim_id"], m["value"],
                                        ",".join(m["conditions"]) or "no condition")
                        for m in c["claims"]), c["resolution"]]
             for c in graph["conflicts"]]))
    if graph["unreported"]:
        parts.append("<h3>4.4 unreported list</h3>")
        parts.append(_html_table(
            ["item", "context", "evidence"],
            [[u["item"], u["context"],
              ";".join(_ev_ref(e) for e in u["evidence"])]
             for u in graph["unreported"]]))

    # 5. verification summary
    st = verified["stats"]
    parts.append("<h2>5. Mechanical verification summary</h2>")
    parts.append("<p>extraction lines: %d total · %d accepted · %d rejected "
                 "(%s). Every quote above was re-checked as an exact substring "
                 "of the cited paragraph: %d/%d verified.</p>"
                 % (st["total_lines"], st["accepted"], st["rejected"],
                    hesc(", ".join("%s=%d" % (k, st["by_reason"][k])
                                   for k in sorted(st["by_reason"])) or "none"),
                    evidence_index["stats"]["quote_verified"],
                    evidence_index["stats"]["entries"]))
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def build_md(graph, queries, evidence_index, verified):
    L = []
    L.append("# KG delivery report — `%s`" % graph["case_id"])
    if graph["synthetic"]:
        L.append("")
        L.append("> ⚠ **SYNTHETIC example output** — demonstrates the deliverable "
                 "set only; NOT a real-paper answer.")
    L.append("")
    L.append("produced by `%s` · stdlib-only deterministic layout · "
             "%d nodes / %d edges / %d merges / %d non-merges / %d conflicts preserved"
             % (SCHEMA_VERSION, graph["stats"]["nodes"], graph["stats"]["edges"],
                graph["stats"]["merges"], graph["stats"]["nonmerges"],
                graph["stats"]["conflicts"]))
    L.append("")
    L.append("## Full graph")
    L.append("")
    L.append("see `graph.svg` (%d nodes, %d edges)"
             % (graph["stats"]["nodes"], graph["stats"]["edges"]))
    L.append("")
    L.append("## Queries")
    for q in queries["queries"]:
        L.append("")
        L.append("### %s — %s (%s)" % (q["id"], q["type"], q["status"]))
        L.append("")
        L.append("- params: `%s`" % json.dumps(q["params"], ensure_ascii=False,
                                               sort_keys=True))
        L.append("- svg: `query_%s.svg`" % q["id"])
        L.append("- result: %d node(s), %d edge(s)" % (len(q["nodes"]),
                                                       len(q["edges"])))
        for p in q["paths"]:
            L.append("- path: " + " → ".join(p["nodes"]))
        for c in q["conflict_check"]:
            L.append("- conflict preserved on %s: %s (resolution=%s)"
                     % (c["metric_label"], ", ".join(c["distinct_values"]),
                        c["resolution"]))
        for u in q["undetermined"]:
            L.append("- undetermined: **%s** — %s" % (u["item"], u["reason"]))
    L.append("")
    L.append("## Merges / non-merges / unreported")
    for m in graph["merges"]:
        L.append("- MERGE %s <- %s (key `%s`): %s"
                 % (m["keep"], m["drop"], m["key"], m["reason"]))
    for x in graph["nonmerges"]:
        L.append("- NON-MERGE %s ≠ %s (key `%s`): %s"
                 % (x["a"], x["b"], x["normalized_key"], x["reason"]))
    for u in graph["unreported"]:
        L.append("- UNREPORTED: %s — %s" % (u["item"], u["context"]))
    L.append("")
    L.append("## Evidence index")
    L.append("")
    L.append("%d/%d quotes mechanically re-verified as exact substrings; full "
             "table in `report.html` and `evidence_index.json`."
             % (evidence_index["stats"]["quote_verified"],
                evidence_index["stats"]["entries"]))
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# render_all
# ---------------------------------------------------------------------------

def render_all(work_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    graph = _read(os.path.join(work_dir, "graph.json"))
    queries = _read(os.path.join(work_dir, "queries.json"))
    corpus = _read(os.path.join(work_dir, "corpus.json"))
    verified = _read(os.path.join(work_dir, "verified.json"))

    written = []

    def put(name, text):
        with open(os.path.join(out_dir, name), "w", encoding="utf-8") as fh:
            fh.write(text)
        written.append(name)

    subtitle = ("SYNTHETIC example — not real papers | " if graph["synthetic"] else "")
    subtitle += ("nodes=%d edges=%d | layered by entity type, sorted within layer"
                 % (graph["stats"]["nodes"], graph["stats"]["edges"]))

    svgs = {"graph.svg": render_svg(graph, "Full knowledge graph — %s"
                                    % graph["case_id"], subtitle)}
    put("graph.svg", svgs["graph.svg"])

    query_svgs = {}
    for q in queries["queries"]:
        name = "query_%s.svg" % q["id"]
        query_svgs[name] = render_svg(
            graph, "Query %s — %s (highlighted subgraph)" % (q["id"], q["type"]),
            subtitle + " | status=%s | result: %d nodes, %d edges"
            % (q["status"], len(q["nodes"]), len(q["edges"])),
            highlight_nodes=q["nodes"], highlight_edges=q["edges"])
        put(name, query_svgs[name])

    evidence_index = build_evidence_index(graph, corpus)
    put("evidence_index.json",
        json.dumps(evidence_index, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n")
    put("verification_report.json",
        json.dumps({"schema": SCHEMA_VERSION, "stats": verified["stats"],
                    "rejected": verified["rejected"]},
                   ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    write_csvs(graph, out_dir)
    written += ["nodes.csv", "edges.csv"]
    write_jsonld(graph, out_dir)
    written.append("graph.jsonld")
    write_graphml(graph, out_dir)
    written.append("graph.graphml")
    put("report.html", build_html(graph, queries, evidence_index, verified,
                                  svgs, query_svgs))
    put("report.md", build_md(graph, queries, evidence_index, verified))
    return sorted(written)


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="render.py",
        description="Render the full deliverable set (SVG/HTML/MD/CSV/JSON-LD/"
                    "GraphML/evidence index) from a verified graph. Stdlib only.")
    ap.add_argument("--work", required=True,
                    help="work dir containing graph.json, queries.json, "
                         "corpus.json, verified.json")
    ap.add_argument("--output", required=True, help="output dir for artifacts")
    args = ap.parse_args(argv)
    written = render_all(args.work, args.output)
    for name in written:
        print("wrote", os.path.join(args.output, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
