#!/usr/bin/env python3
"""Deterministic, source-bound SVG publication builder. Python standard library only."""
from __future__ import annotations
import argparse, csv, hashlib, heapq, html, json, math, re, shutil, sys
from pathlib import Path
from xml.etree import ElementTree as ET

VERSION = "1.0.0"
PALETTE = {
    "material": {"color": "#0072B2", "dash": "none", "marker": "arrow", "label": "Material flow"},
    "energy": {"color": "#D55E00", "dash": "9 6", "marker": "arrow", "label": "Energy flow"},
    "information": {"color": "#6A51A3", "dash": "2 5", "marker": "arrow", "label": "Information flow"},
    "activation": {"color": "#15803D", "dash": "none", "marker": "arrow", "label": "Activation"},
    "inhibition": {"color": "#B91C1C", "dash": "none", "marker": "bar", "label": "Inhibition"},
    "flow": {"color": "#0072B2", "dash": "none", "marker": "arrow", "label": "Material flow"},
}
GLYPHS = {"reservoir", "pump", "reactor", "sensor", "detector", "column", "cell", "valve", "sample", "process", "output"}
class StudioError(Exception): pass

def load_json(path):
    try:
        with open(path, encoding="utf-8") as f: return json.load(f)
    except (OSError, json.JSONDecodeError) as e: raise StudioError(f"Cannot read JSON {path}: {e}")

def dump_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def esc(s): return html.escape(str(s), quote=True)
def sha256(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def num(x, name):
    try: v = float(x)
    except (TypeError, ValueError): raise StudioError(f"{name} must be numeric, got {x!r}")
    if not math.isfinite(v): raise StudioError(f"{name} must be finite")
    return v

def text_units(s):
    import unicodedata
    return sum(1.0 if unicodedata.east_asian_width(c) in "WF" else (0.30 if c == " " else 0.56) for c in str(s))

def tokenize_label(s):
    # English phrases stay word-wrapped; CJK and long unbroken tokens can wrap by character.
    tokens, buf = [], ""
    for c in str(s):
        import unicodedata
        if unicodedata.east_asian_width(c) in "WF":
            if buf: tokens.append(buf); buf = ""
            tokens.append(c)
        elif c == " ":
            if buf: tokens.append(buf); buf = ""
            tokens.append(" ")
        else: buf += c
    if buf: tokens.append(buf)
    return tokens

def wrap_label(text, max_px, font_size, max_lines):
    tokens, lines, current = tokenize_label(text), [], ""
    for token in tokens:
        candidate = current + token
        if current and text_units(candidate) * font_size > max_px:
            lines.append(current.rstrip()); current = token.lstrip()
            if text_units(current) * font_size > max_px:
                piece = ""
                for c in current:
                    if piece and text_units(piece + c) * font_size > max_px:
                        lines.append(piece); piece = c
                    else: piece += c
                current = piece
        else: current = candidate
    if current or not lines: lines.append(current.rstrip())
    if len(lines) > max_lines:
        raise StudioError(f"Label overflow: {text!r} needs {len(lines)} lines; maximum is {max_lines}. Increase node/canvas or shorten the source-faithful label.")
    return lines

def text_svg(text_id, x, y, text, max_px, size=18, weight=400, anchor="middle", cls="label", max_lines=3, fill="#172033"):
    lines = wrap_label(text, max_px, size, max_lines)
    spans = []
    for i, line in enumerate(lines):
        dy = 0 if i == 0 else size * 1.22
        spans.append(f'<tspan x="{x:.2f}" dy="{dy:.2f}">{esc(line)}</tspan>')
    return f'<text id="{esc(text_id)}" class="{cls}" x="{x:.2f}" y="{y:.2f}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{fill}">' + "".join(spans) + "</text>"

def normalize_spec(spec):
    if not isinstance(spec, dict): raise StudioError("Source spec must be a JSON object")
    canvas = spec.get("canvas", {})
    w, h = num(canvas.get("width", 1600), "canvas.width"), num(canvas.get("height", 1000), "canvas.height")
    if w < 480 or h < 320: raise StudioError("Canvas must be at least 480 x 320 SVG units")
    nodes, edges = spec.get("nodes", []), spec.get("edges", [])
    if not nodes: raise StudioError("At least one node is required")
    ids = []
    for n in nodes:
        if not isinstance(n, dict) or not n.get("id") or not n.get("label"): raise StudioError("Every node requires id and label")
        ids.append(n["id"])
        if n.get("kind", "process") not in GLYPHS: raise StudioError(f"Unknown node glyph {n.get('kind')!r}")
    if len(ids) != len(set(ids)): raise StudioError("Duplicate node id")
    node_ids = set(ids)
    for e in edges:
        if not e.get("id") or e.get("from") not in node_ids or e.get("to") not in node_ids: raise StudioError(f"Edge has missing/unknown endpoint: {e}")
        if e["from"] == e["to"]: raise StudioError("Self loops are not supported; split into explicit nodes")
        if e.get("kind", "material") not in PALETTE: raise StudioError(f"Unknown edge encoding {e.get('kind')!r}")
    if len([e["id"] for e in edges]) != len(edges) or len(set(e["id"] for e in edges)) != len(edges): raise StudioError("Edges require unique ids")
    return w, h

def automatic_ranks(nodes, edges):
    explicit = {n["id"]: int(n["rank"]) for n in nodes if "rank" in n}
    if len(explicit) == len(nodes): return explicit
    ids = [n["id"] for n in nodes]
    # Ranking uses forward process/material edges; information feedback must not create false rank cycles.
    candidates = [e for e in edges if e.get("kind", "material") in ("material", "flow", "activation", "inhibition")]
    indeg = {i: 0 for i in ids}; outgoing = {i: [] for i in ids}
    for e in candidates:
        if e["from"] not in explicit and e["to"] not in explicit:
            outgoing[e["from"]].append(e["to"]); indeg[e["to"]] += 1
    rank = {i: explicit.get(i, 0) for i in ids}
    queue = [i for i in ids if indeg[i] == 0]; seen = 0
    while queue:
        u = queue.pop(0); seen += 1
        for v in outgoing[u]:
            rank[v] = max(rank[v], rank[u] + 1); indeg[v] -= 1
            if indeg[v] == 0: queue.append(v)
    if seen != len(ids):
        raise StudioError("Cycle prevents automatic ranking. Add explicit nondecreasing rank values or mark the feedback edge kind=information.")
    return rank

def layout_nodes(spec):
    nodes, edges = spec["nodes"], spec["edges"]
    ranks = automatic_ranks(nodes, edges)
    lanes = sorted(set(int(n.get("lane", 0)) for n in nodes))
    region = spec.get("diagram", {})
    rx, ry = num(region.get("x", 60), "diagram.x"), num(region.get("y", 150), "diagram.y")
    rw, rh = num(region.get("width", 1480), "diagram.width"), num(region.get("height", 420), "diagram.height")
    min_rank, max_rank = min(ranks.values()), max(ranks.values())
    placed, occupied = {}, set()
    for index, n in enumerate(nodes):
        n = dict(n); n["rank"] = ranks[n["id"]]; n["lane"] = int(n.get("lane", 0))
        key = (n["rank"], n["lane"])
        if key in occupied: raise StudioError(f"Two nodes occupy rank/lane {key}; supply distinct lanes")
        occupied.add(key)
        nw, nh = num(n.get("width", 176), "node.width"), num(n.get("height", 120), "node.height")
        x = rx + nw / 2 if max_rank == min_rank else rx + nw / 2 + (rw - nw) * (n["rank"] - min_rank) / (max_rank - min_rank)
        lane_index = lanes.index(n["lane"])
        usable_top, usable_bottom = ry + 54, ry + rh - 24
        y = usable_top + nh / 2 if len(lanes) == 1 else usable_top + nh / 2 + (usable_bottom - usable_top - nh) * lane_index / (len(lanes) - 1)
        if x - nw/2 < 0 or y - nh/2 < 0: raise StudioError(f"Node {n['id']} overflows canvas")
        n.update(x=x, y=y, w=nw, h=nh); placed[n["id"]] = n
    return placed

def glyph_svg(n):
    x, y, w, h, kind = n["x"], n["y"], n["w"], n["h"], n.get("kind", "process")
    left, top = x - w/2, y - h/2
    out = [f'<rect class="node-box" x="{left:.2f}" y="{top:.2f}" width="{w:.2f}" height="{h:.2f}" rx="14"/>']
    gx, gy = left + 28, y - 22
    common = 'fill="#F8FAFC" stroke="#334155" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"'
    if kind == "reservoir":
        out += [f'<path d="M {gx-15} {gy-17} h30 v34 q0 8 -8 8 h-14 q-8 0 -8 -8 z" {common}/>', f'<path d="M {gx-13} {gy+7} q7 -5 14 0 t14 0" fill="none" stroke="#0072B2" stroke-width="2.4"/>']
    elif kind == "pump":
        out += [f'<circle cx="{gx}" cy="{gy+4}" r="22" {common}/>', f'<path d="M {gx-8} {gy-8} l19 12 -19 12 z" fill="#0072B2"/>']
    elif kind in ("reactor", "column"):
        out += [f'<rect x="{gx-15}" y="{gy-24}" width="30" height="52" rx="12" {common}/>', f'<path d="M {gx-13} {gy+9} h26 M {gx} {gy-24} v-8 M {gx} {gy+28} v8" stroke="#D55E00" stroke-width="2.4" fill="none"/>']
    elif kind in ("sensor", "detector"):
        out += [f'<circle cx="{gx}" cy="{gy+2}" r="21" {common}/>', f'<path d="M {gx-13} {gy+8} q13 -25 26 0 M {gx} {gy+2} l10 -10" fill="none" stroke="#6A51A3" stroke-width="2.4"/>']
    elif kind == "valve":
        out += [f'<path d="M {gx-22} {gy-12} l22 15 -22 15 z M {gx+22} {gy-12} l-22 15 22 15 z" {common}/>', f'<path d="M {gx} {gy+3} v-25 h14" stroke="#B91C1C" stroke-width="2.4" fill="none"/>']
    elif kind == "cell":
        out += [f'<ellipse cx="{gx}" cy="{gy+3}" rx="23" ry="20" fill="#ECFDF5" stroke="#15803D" stroke-width="2.2"/>', f'<circle cx="{gx+5}" cy="{gy}" r="7" fill="#86EFAC" stroke="#15803D"/>']
    else:
        out += [f'<path d="M {gx-22} {gy-18} h44 v40 h-44 z M {gx-13} {gy-7} h26 M {gx-13} {gy+4} h19" {common}/>']
    label_y = y + 7
    label_size = n.get("font_size", 17)
    label_lines = wrap_label(n["label"], w - 88, label_size, int(n.get("max_label_lines", 2)))
    out.append(text_svg(f"node-{n['id']}-label", x + 18, label_y, n["label"], w - 88, size=label_size, weight=650, max_lines=int(n.get("max_label_lines", 2))))
    if n.get("sublabel"):
        sublabel_y = label_y + (len(label_lines)-1)*label_size*1.22 + 20
        out.append(text_svg(f"node-{n['id']}-sublabel", x + 18, sublabel_y, n["sublabel"], w - 88, size=12, max_lines=1, fill="#475569"))
    return "".join(out)

def segment_hits_rect(a, b, r, pad=5):
    # Segments in the routing grid are horizontal or vertical; nodes are forbidden obstacles.
    x1, y1 = a; x2, y2 = b
    left, right = r["x"]-r["w"]/2-pad, r["x"]+r["w"]/2+pad
    top, bottom = r["y"]-r["h"]/2-pad, r["y"]+r["h"]/2+pad
    if abs(x1-x2) < 1e-6:
        return left < x1 < right and max(min(y1,y2), top) < min(max(y1,y2), bottom)
    if abs(y1-y2) < 1e-6:
        return top < y1 < bottom and max(min(x1,x2), left) < min(max(x1,x2), right)
    return True

def ortho_route(source, target, nodes, region, edge_index):
    forward = target["x"] >= source["x"]
    if forward:
        s = (source["x"]+source["w"]/2, source["y"]); t = (target["x"]-target["w"]/2, target["y"])
    else:
        # Feedback uses a lower bus rather than pretending to be forward material flow.
        s = (source["x"], source["y"]+source["h"]/2); t = (target["x"], target["y"]+target["h"]/2)
    if abs(s[1]-t[1]) < 1e-6 and not any(segment_hits_rect(s,t,n) for n in nodes.values() if n["id"] not in (source["id"],target["id"])):
        return [s,t]
    xs = {region["x"]+6, region["x"]+region["width"]-6, s[0], t[0]}
    ys = {region["y"]+46 + (edge_index%4)*7, region["y"]+region["height"]-12-(edge_index%4)*7, s[1], t[1]}
    for n in nodes.values():
        xs.update([n["x"]-n["w"]/2-12, n["x"]+n["w"]/2+12])
        ys.update([n["y"]-n["h"]/2-16-(edge_index%3)*6, n["y"]+n["h"]/2+16+(edge_index%3)*6])
    xs, ys = sorted(xs), sorted(ys)
    start = (min(range(len(xs)),key=lambda i:abs(xs[i]-s[0])), min(range(len(ys)),key=lambda i:abs(ys[i]-s[1])))
    goal = (min(range(len(xs)),key=lambda i:abs(xs[i]-t[0])), min(range(len(ys)),key=lambda i:abs(ys[i]-t[1])))
    # Direction-aware Dijkstra: geometric length + bend penalty; deterministic tie breaking.
    pq, dist, prev = [(0, start[0], start[1], 4)], {}, {}
    dist[(start[0],start[1],4)] = 0
    final = None
    while pq:
        cost, ix, iy, direction = heapq.heappop(pq)
        if cost != dist.get((ix,iy,direction)): continue
        if (ix,iy) == goal: final=(ix,iy,direction); break
        for nd, dx, dy in ((0,1,0),(1,0,1),(2,-1,0),(3,0,-1)):
            nx, ny = ix+dx, iy+dy
            if not (0 <= nx < len(xs) and 0 <= ny < len(ys)): continue
            a,b=(xs[ix],ys[iy]),(xs[nx],ys[ny])
            if any(segment_hits_rect(a,b,n) for n in nodes.values() if n["id"] not in (source["id"],target["id"])): continue
            nc = cost + abs(a[0]-b[0])+abs(a[1]-b[1]) + (36 if direction != 4 and direction != nd else 0)
            state=(nx,ny,nd)
            if nc < dist.get(state, float("inf")):
                dist[state]=nc; prev[state]=(ix,iy,direction); heapq.heappush(pq,(nc,nx,ny,nd))
    if final is None: raise StudioError(f"No collision-free orthogonal route from {source['id']} to {target['id']}; adjust lanes or diagram region")
    states=[final]
    while states[-1] != (start[0],start[1],4): states.append(prev[states[-1]])
    states.reverse(); points=[s]+[(xs[a],ys[b]) for a,b,_ in states]+[t]
    clean=[]
    for p in points:
        if clean and abs(clean[-1][0]-p[0])<1e-6 and abs(clean[-1][1]-p[1])<1e-6: continue
        if len(clean)>=2:
            a,b=clean[-2],clean[-1]
            if (abs(a[0]-b[0])<1e-6 and abs(b[0]-p[0])<1e-6) or (abs(a[1]-b[1])<1e-6 and abs(b[1]-p[1])<1e-6): clean[-1]=p; continue
        clean.append(p)
    return clean

def edge_svg(e, points):
    enc = PALETTE[e.get("kind", "material")]
    d = "M " + " L ".join(f"{x:.2f} {y:.2f}" for x,y in points)
    dash = "" if enc["dash"] == "none" else f' stroke-dasharray="{enc["dash"]}"'
    marker = "bar-inhibition" if enc["marker"] == "bar" else "arrow-" + e.get("kind", "material")
    label = e.get("label", enc["label"])
    segments = list(zip(points, points[1:]))
    horizontal = [s for s in segments if abs(s[0][1]-s[1][1]) < 1e-6]
    candidates = horizontal if any(abs(a[0]-b[0]) > 30 for a,b in horizontal) else segments
    a,b = max(candidates, key=lambda s: abs(s[0][0]-s[1][0])+abs(s[0][1]-s[1][1]))
    mid = ((a[0]+b[0])/2, (a[1]+b[1])/2)
    out = [f'<path id="edge-{esc(e["id"])}" class="relation relation-{esc(e.get("kind","material"))}" d="{d}" fill="none" stroke="{enc["color"]}" stroke-width="3"{dash} marker-end="url(#{marker})"><title>{esc(label)}: {esc(e["from"])} to {esc(e["to"])}</title></path>']
    if e.get("label"):
        out.append(text_svg(f"edge-{e['id']}-label", mid[0], mid[1]-9, e["label"], 160, size=12, max_lines=1, fill=enc["color"]))
    return "".join(out)

def chart_svg(spec, spec_dir, output_dir):
    charts = spec.get("charts", [])
    if not charts: return "", [], []
    out, mappings, copied = [], [], []
    for ci, chart in enumerate(charts):
        csv_value = chart.get("data_csv")
        if not csv_value: raise StudioError("Chart requires data_csv")
        csv_path = (Path(spec_dir) / csv_value).resolve()
        try: f = open(csv_path, encoding="utf-8-sig", newline="")
        except OSError as e: raise StudioError(f"Cannot open chart CSV {csv_path}: {e}")
        with f:
            reader=csv.DictReader(f)
            if not reader.fieldnames: raise StudioError(f"Chart CSV {csv_path} has no header")
            xcol=chart.get("x_column"); ycols=chart.get("y_columns",[])
            if not xcol or xcol not in reader.fieldnames: raise StudioError(f"Chart x_column {xcol!r} not present in CSV columns {reader.fieldnames}")
            if not ycols or not isinstance(ycols,list): raise StudioError("Chart y_columns must be a nonempty list")
            for s in ycols:
                if not s.get("column") or s["column"] not in reader.fieldnames: raise StudioError(f"Chart y column {s.get('column')!r} not present in CSV columns {reader.fieldnames}")
            rows=[]
            for line,row in enumerate(reader,2):
                try: x=num(row[xcol],f"CSV line {line} {xcol}"); ys=[num(row[s["column"]],f"CSV line {line} {s['column']}") for s in ycols]
                except KeyError as e: raise StudioError(f"Malformed CSV line {line}: missing {e}")
                rows.append((x,ys))
        if len(rows)<2: raise StudioError("Chart CSV needs at least two valid data rows")
        rows.sort(key=lambda r:r[0])
        if len(set(r[0] for r in rows)) != len(rows): raise StudioError("Chart x values must be unique")
        box=chart.get("box",{}); x0=num(box.get("x",100),"chart.box.x"); y0=num(box.get("y",680),"chart.box.y"); w=num(box.get("width",1400),"chart.box.width"); h=num(box.get("height",250),"chart.box.height")
        ml,mr,mt,mb=90,35,78,58; px,py=x0+ml,y0+mt; pw,ph=w-ml-mr,h-mt-mb
        if pw<100 or ph<80: raise StudioError("Chart plot area is too small")
        all_y=[v for _,ys in rows for v in ys]; ymin,ymax=num(chart.get("y_min",min(all_y)),"y_min"),num(chart.get("y_max",max(all_y)),"y_max")
        xmin,xmax=num(chart.get("x_min",rows[0][0]),"x_min"),num(chart.get("x_max",rows[-1][0]),"x_max")
        if xmin==xmax or ymin==ymax: raise StudioError("Chart ranges must be nonzero")
        if ymin>ymax or xmin>xmax: raise StudioError("Chart min exceeds max")
        def X(v): return px+(v-xmin)/(xmax-xmin)*pw
        def Y(v): return py+ph-(v-ymin)/(ymax-ymin)*ph
        cid=chart.get("id",f"chart-{ci+1}")
        out.append(f'<g id="panel-{esc(cid)}" class="chart-panel"><rect x="{x0}" y="{y0}" width="{w}" height="{h}" rx="18" class="panel"/>')
        out.append(text_svg(f"{cid}-title",x0+22,y0+28,chart.get("title","Chart"),w-44,size=18,weight=700,anchor="start",max_lines=1))
        out.append(f'<text x="{x0+24}" y="{y0+51}" class="panel-tag">PANEL B · DATA FROM CSV</text>')
        for ti in range(5):
            val=ymin+(ymax-ymin)*ti/4; yy=Y(val)
            out.append(f'<line x1="{px}" y1="{yy:.2f}" x2="{px+pw}" y2="{yy:.2f}" class="grid"/>')
            out.append(f'<text x="{px-12}" y="{yy+5:.2f}" class="tick" text-anchor="end">{val:.3g}</text>')
        for ti in range(5):
            val=xmin+(xmax-xmin)*ti/4; xx=X(val)
            out.append(f'<line x1="{xx:.2f}" y1="{py}" x2="{xx:.2f}" y2="{py+ph}" class="grid vertical"/>')
            out.append(f'<text x="{xx:.2f}" y="{py+ph+24}" class="tick" text-anchor="middle">{val:.3g}</text>')
        out.append(f'<line x1="{px}" y1="{py+ph}" x2="{px+pw}" y2="{py+ph}" class="axis"/><line x1="{px}" y1="{py}" x2="{px}" y2="{py+ph}" class="axis"/>')
        out.append(text_svg(f"{cid}-xlabel",px+pw/2,py+ph+48,chart.get("x_label",xcol),pw,size=14,max_lines=1))
        out.append(f'<text x="{x0+23}" y="{py+ph/2}" class="axis-title" text-anchor="middle" transform="rotate(-90 {x0+23} {py+ph/2})">{esc(chart.get("y_label", "Value"))}</text>')
        colors=["#0072B2","#D55E00","#6A51A3","#15803D","#B91C1C"]; dashes=["none","9 6","2 5","12 4 2 4","3 3"]
        legend=[]
        for si,s in enumerate(ycols):
            vals=[(r[0],r[1][si]) for r in rows]; points=" ".join(f"{X(a):.2f},{Y(b):.2f}" for a,b in vals)
            color=s.get("color",colors[si%len(colors)]); dash=s.get("dash",dashes[si%len(dashes)]); da="" if dash=="none" else f' stroke-dasharray="{dash}"'
            out.append(f'<polyline id="{cid}-series-{esc(s["column"])}" points="{points}" fill="none" stroke="{color}" stroke-width="3"{da} stroke-linejoin="round" stroke-linecap="round"/>')
            for pi,(a,b) in enumerate(vals): out.append(f'<circle cx="{X(a):.2f}" cy="{Y(b):.2f}" r="4" fill="#FFFFFF" stroke="{color}" stroke-width="2.5"><title>{esc(s["column"])}; {esc(xcol)}={a:g}; value={b:g}</title></circle>')
            legend.append((s.get("label",s["column"]),color,dash))
        total=sum(max(150,text_units(v[0])*14+65) for v in legend); lx=px+pw-total
        for i,(label,color,dash) in enumerate(legend):
            da="" if dash=="none" else f' stroke-dasharray="{dash}"'; itemw=max(150,text_units(label)*14+65)
            out.append(f'<line x1="{lx}" y1="{y0+28}" x2="{lx+34}" y2="{y0+28}" stroke="{color}" stroke-width="3"{da}/><circle cx="{lx+17}" cy="{y0+28}" r="3.5" fill="#fff" stroke="{color}" stroke-width="2"/><text x="{lx+43}" y="{y0+33}" class="legend-text">{esc(label)}</text>')
            lx+=itemw
        out.append('</g>')
        mappings.append({"chart_id":cid,"csv":csv_path.name,"x_column":xcol,"series":[{"column":s["column"],"label":s.get("label",s["column"]),"rows":len(rows)} for s in ycols],"x_range":[xmin,xmax],"y_range":[ymin,ymax]})
        dest=Path(output_dir)/csv_path.name
        if csv_path != dest.resolve(): shutil.copyfile(csv_path,dest)
        copied.append(csv_path.name)
    return "".join(out), mappings, copied

def build_svg(spec, spec_dir, output_dir):
    w,h=normalize_spec(spec); placed=layout_nodes(spec)
    region=spec.get("diagram",{}); rx=num(region.get("x",60),"diagram.x"); ry=num(region.get("y",150),"diagram.y"); rw=num(region.get("width",1480),"diagram.width"); rh=num(region.get("height",420),"diagram.height")
    for n in placed.values():
        if n["x"]+n["w"]/2>w or n["y"]+n["h"]/2>h: raise StudioError(f"Node {n['id']} overflows canvas")
    chart,mappings,copied=chart_svg(spec,spec_dir,output_dir)
    title=spec.get("title","Scientific publication figure"); subtitle=spec.get("subtitle","Source-bound vector artwork")
    used=[]
    for e in spec.get("edges",[]):
        if e.get("kind","material") not in used: used.append(e.get("kind","material"))
    defs=['<defs>']
    for kind in sorted(set(list(used)+["material"])):
        color=PALETTE[kind]["color"]
        defs.append(f'<marker id="arrow-{kind}" viewBox="0 0 12 12" refX="10" refY="6" markerWidth="10" markerHeight="10" orient="auto-start-reverse"><path d="M 1 1 L 11 6 L 1 11 z" fill="{color}"/></marker>')
    defs.append('<marker id="bar-inhibition" viewBox="0 0 12 14" refX="10" refY="7" markerWidth="10" markerHeight="12" orient="auto"><path d="M 10 1 V 13" stroke="#B91C1C" stroke-width="3.4"/></marker>')
    defs.append('</defs>')
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" id="vector-publication-figure" width="{spec.get("canvas",{}).get("physical_width",w/5):g}mm" height="{spec.get("canvas",{}).get("physical_height",h/5):g}mm" viewBox="0 0 {w:g} {h:g}" role="img" aria-labelledby="figure-title figure-desc">',
         f'<title id="figure-title">{esc(title)}</title><desc id="figure-desc">{esc(spec.get("description",subtitle))}</desc>',"".join(defs),
         '<g id="layer-background"><rect width="100%" height="100%" fill="#FFFFFF"/></g>',
         '<g id="layer-headings">'+text_svg("figure-heading",60,55,title,w-120,size=30,weight=750,anchor="start",max_lines=2)+text_svg("figure-subheading",60,93,subtitle,w-120,size=16,anchor="start",max_lines=2,fill="#475569")+'</g>',
         f'<g id="layer-diagram"><rect x="{rx}" y="{ry}" width="{rw}" height="{rh}" rx="18" class="panel"/><text x="{rx+22}" y="{ry+30}" class="panel-tag">PANEL A · APPARATUS / ROUTE</text>']
    routes=[]
    for i,e in enumerate(spec.get("edges",[])):
        pts=ortho_route(placed[e["from"]],placed[e["to"]],placed,{"x":rx,"y":ry,"width":rw,"height":rh},i)
        out.append(edge_svg(e,pts)); routes.append({"id":e["id"],"from":e["from"],"to":e["to"],"kind":e.get("kind","material"),"points":[[round(a,3),round(b,3)] for a,b in pts]})
    for n in placed.values(): out.append(f'<g id="node-{esc(n["id"])}" class="apparatus-node glyph-{esc(n.get("kind","process"))}" data-rank="{n["rank"]}" data-lane="{n["lane"]}"><title>{esc(n["label"])}</title>{glyph_svg(n)}</g>')
    out.append('</g>')
    out.append('<g id="layer-charts">'+chart+'</g>')
    out.append('<g id="layer-legend"><rect x="60" y="112" width="'+str(min(w-120,max(420,len(used)*225)))+'" height="30" rx="15" fill="#F8FAFC"/>')
    lx=80
    for kind in used:
        enc=PALETTE[kind]; dash="" if enc["dash"]=="none" else f' stroke-dasharray="{enc["dash"]}"'; marker="bar-inhibition" if enc["marker"]=="bar" else "arrow-"+kind
        out.append(f'<line x1="{lx}" y1="127" x2="{lx+36}" y2="127" stroke="{enc["color"]}" stroke-width="3"{dash} marker-end="url(#{marker})"/><text x="{lx+48}" y="132" class="legend-text">{esc(enc["label"])}</text>'); lx+=225
    out.append('</g>')
    footer=spec.get("footer","Live SVG text · vector paths · see source_spec.json for provenance and data mapping")
    out.append('<g id="layer-footer">'+text_svg("figure-footer",60,h-24,footer,w-120,size=12,anchor="start",max_lines=1,fill="#64748B")+'</g></svg>')
    metadata={"version":VERSION,"nodes":placed,"routes":routes,"data_mappings":mappings,"copied_csv":copied,"font_embedding":False}
    return "\n".join(out)+"\n",metadata

STYLE='''<style><![CDATA[
text { font-family: "Noto Sans", "Source Han Sans SC", "Arial", sans-serif; }
.panel { fill: #FFFFFF; stroke: #CBD5E1; stroke-width: 1.5; }
.node-box { fill: #F8FAFC; stroke: #64748B; stroke-width: 1.5; }
.panel-tag { font: 700 12px "Arial", sans-serif; letter-spacing: 1.4px; fill: #475569; }
.tick { font: 12px "Arial", sans-serif; fill: #475569; }
.axis { stroke: #334155; stroke-width: 1.7; }
.grid { stroke: #E2E8F0; stroke-width: 1; }
.grid.vertical { stroke-dasharray: 2 5; }
.axis-title, .legend-text { font: 13px "Arial", sans-serif; fill: #334155; }
]]></style>'''

def build_command(args):
    spec_path=Path(args.spec).resolve(); spec=load_json(spec_path); out=Path(args.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    svg,metadata=build_svg(spec,spec_path.parent,out)
    # Insert static styles without impacting any source text or relationship semantics.
    svg=svg.replace("<defs>",STYLE+"<defs>",1)
    svg_path=out/(args.basename+".svg"); svg_path.write_text(svg,encoding="utf-8")
    copied_spec=dict(spec)
    if spec.get("charts"):
        copied_spec["charts"]=[dict(c,data_csv=Path(c["data_csv"]).name) for c in spec["charts"]]
    dump_json(out/"source_spec.json",copied_spec); dump_json(out/"layout_manifest.json",metadata)
    print(json.dumps({"status":"ok","svg":str(svg_path),"nodes":len(spec["nodes"]),"edges":len(spec.get("edges",[])),"csv":metadata["copied_csv"]}))
    return 0

def detect_exporters():
    import importlib.util
    mac_chrome="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    mac_inkscape="/Applications/Inkscape.app/Contents/MacOS/inkscape"
    return {"cairosvg":bool(importlib.util.find_spec("cairosvg")),"rsvg-convert":shutil.which("rsvg-convert"),"inkscape":shutil.which("inkscape") or (mac_inkscape if Path(mac_inkscape).is_file() else None),"chrome":shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome") or (mac_chrome if Path(mac_chrome).is_file() else None)}

def chrome_export(executable,svg,png,pdf):
    import subprocess, tempfile
    with tempfile.TemporaryDirectory(prefix="vps-chrome-") as td:
        profile=Path(td)/"profile"; html_path=Path(td)/"preview.html"
        uri=Path(svg).resolve().as_uri()
        root=ET.parse(svg).getroot(); physical_w=root.get("width","320mm"); physical_h=root.get("height","200mm")
        page_size=physical_w+" "+physical_h
        html_path.write_text('<!doctype html><html><head><meta charset="utf-8"><style>@page{size:'+page_size+';margin:0}html,body{margin:0;width:100%;height:100%;overflow:hidden}img{display:block;width:100vw;height:100vh;object-fit:contain}@media print{img{width:'+physical_w+';height:'+physical_h+'}}</style></head><body><img src="'+html.escape(uri,quote=True)+'"></body></html>',encoding="utf-8")
        base=[executable,"--headless","--disable-gpu","--disable-dev-shm-usage","--allow-file-access-from-files","--run-all-compositor-stages-before-draw","--virtual-time-budget=1500","--user-data-dir="+str(profile)]
        if png:
            cmd=base+["--hide-scrollbars","--window-size=2400,1500","--screenshot="+str(png),html_path.as_uri()]
            r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
            if r.returncode or not Path(png).is_file(): raise StudioError("Chrome PNG export failed: "+r.stderr.decode("utf-8","replace")[-800:])
        if pdf:
            cmd=base+["--no-pdf-header-footer","--print-to-pdf="+str(pdf),html_path.as_uri()]
            r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
            if r.returncode or not Path(pdf).is_file(): raise StudioError("Chrome PDF export failed: "+r.stderr.decode("utf-8","replace")[-800:])

def export_files(svg, png=None, pdf=None):
    import subprocess
    checks=[]; failures=[]; exporters=detect_exporters()
    if not (png or pdf): return {"exporters_detected":exporters,"used":checks,"attempt_failures":failures}
    if exporters["cairosvg"]:
        try:
            import cairosvg
            if png: cairosvg.svg2png(url=str(svg),write_to=str(png),scale=1.5)
            if pdf: cairosvg.svg2pdf(url=str(svg),write_to=str(pdf))
            checks.append({"exporter":"CairoSVG","version":getattr(cairosvg,"__version__","unknown")})
        except Exception as e: failures.append({"exporter":"CairoSVG","error":str(e)[-1200:]})
    if not checks and exporters["rsvg-convert"]:
        try:
            if png: subprocess.run([exporters["rsvg-convert"],"-o",str(png),str(svg)],check=True,capture_output=True,timeout=90)
            if pdf: subprocess.run([exporters["rsvg-convert"],"-f","pdf","-o",str(pdf),str(svg)],check=True,capture_output=True,timeout=90)
            checks.append({"exporter":"rsvg-convert","path":exporters["rsvg-convert"]})
        except Exception as e: failures.append({"exporter":"rsvg-convert","error":str(e)[-1200:]})
    if not checks and exporters["inkscape"]:
        try:
            if png: subprocess.run([exporters["inkscape"],str(svg),"--export-type=png","--export-filename="+str(png)],check=True,capture_output=True,timeout=90)
            if pdf: subprocess.run([exporters["inkscape"],str(svg),"--export-type=pdf","--export-filename="+str(pdf)],check=True,capture_output=True,timeout=90)
            checks.append({"exporter":"Inkscape","path":exporters["inkscape"]})
        except Exception as e: failures.append({"exporter":"Inkscape","error":str(e)[-1200:]})
    if not checks and exporters["chrome"]:
        try:
            chrome_export(exporters["chrome"],svg,png,pdf)
            checks.append({"exporter":"Chrome Headless","path":exporters["chrome"],"png_window":[2400,1500],"pdf_page":"SVG physical width/height from @page"})
        except Exception as e: failures.append({"exporter":"Chrome Headless","error":str(e)[-1200:]})
    if not checks: raise StudioError("All requested PNG/PDF exporters failed or are unavailable; no installation attempted. "+json.dumps(failures,ensure_ascii=False))
    return {"exporters_detected":exporters,"used":checks,"attempt_failures":failures}

def verify_png(path):
    b=Path(path).read_bytes()
    if not b.startswith(b"\x89PNG\r\n\x1a\n") or len(b)<45: raise StudioError("PNG signature/header invalid")
    width,height=int.from_bytes(b[16:20],"big"),int.from_bytes(b[20:24],"big")
    if width<1 or height<1 or b[12:16]!=b"IHDR": raise StudioError("PNG IHDR invalid")
    import zlib
    pos=8; chunks=[]; ended=False
    while pos+12<=len(b):
        n=int.from_bytes(b[pos:pos+4],"big"); typ=b[pos+4:pos+8]; data=b[pos+8:pos+8+n]; crc=b[pos+8+n:pos+12+n]
        if len(data)!=n or len(crc)!=4 or zlib.crc32(typ+data)&0xffffffff != int.from_bytes(crc,"big"): raise StudioError(f"PNG chunk {typ!r} CRC/length invalid")
        chunks.append(typ.decode("latin1")); pos+=12+n
        if typ==b"IEND": ended=True; break
    if not ended or "IDAT" not in chunks: raise StudioError("PNG lacks valid IDAT/IEND")
    return {"format":"PNG","bytes":len(b),"pixels":[width,height],"chunk_crc":"pass","idat_iend":"pass","sha256":sha256(path)}

def verify_pdf(path):
    b=Path(path).read_bytes()
    if not b.startswith(b"%PDF-") or b"%%EOF" not in b[-2048:]: raise StudioError("PDF signature/EOF invalid")
    pages=len(re.findall(rb"/Type\s*/Page(?!s)\b",b))
    if pages<1 or b"/MediaBox" not in b: raise StudioError("PDF lacks a page or MediaBox")
    media=re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([0-9.]+)\s+([0-9.]+)\s*\]",b)
    dimensions=None
    if media:
        width_pt,height_pt=float(media.group(1)),float(media.group(2))
        if width_pt<=0 or height_pt<=0: raise StudioError("PDF MediaBox dimensions invalid")
        dimensions={"points":[width_pt,height_pt],"millimetres":[round(width_pt*25.4/72,3),round(height_pt*25.4/72,3)]}
    return {"format":"PDF","bytes":len(b),"page_objects":pages,"media_box":"present","page_dimensions":dimensions,"eof":"present","sha256":sha256(path)}

def verify_svg(path):
    p=Path(path); root=ET.parse(p).getroot(); ns="{http://www.w3.org/2000/svg}"
    if root.tag!=ns+"svg" or not root.get("viewBox") or not root.get("width") or not root.get("height"): raise StudioError("SVG root/viewBox/physical dimensions invalid")
    all_nodes=list(root.iter()); ids=[n.get("id") for n in all_nodes if n.get("id")]
    if len(ids)!=len(set(ids)): raise StudioError("SVG contains duplicate IDs")
    refs=re.findall(r"url\(#([^\)]+)\)",p.read_text(encoding="utf-8"))
    missing=[r for r in refs if r not in ids]
    if missing: raise StudioError(f"Unresolved SVG paint/marker references: {missing}")
    texts=[n for n in all_nodes if n.tag==ns+"text"]
    return {"format":"SVG","bytes":p.stat().st_size,"viewBox":root.get("viewBox"),"physical_width":root.get("width"),"physical_height":root.get("height"),"unique_ids":len(ids),"editable_text_elements":len(texts),"groups":sum(n.tag==ns+"g" for n in all_nodes),"unresolved_references":missing,"fonts_embedded":False,"font_note":"Live SVG text is intentionally editable; fonts are not embedded by this builder. The selected export tool uses available system font substitution. Inspect CJK glyphs in the target renderer.","sha256":sha256(p)}

def export_command(args):
    svg=Path(args.svg).resolve(); out=Path(args.output_dir).resolve(); out.mkdir(parents=True,exist_ok=True)
    png=Path(args.png).resolve() if args.png else None; pdf=Path(args.pdf).resolve() if args.pdf else None
    for p in (png,pdf):
        if p: p.parent.mkdir(parents=True,exist_ok=True)
    report={"status":"complete","svg":verify_svg(svg),"exports":[],"limitations":["SVG fonts are not embedded; live text depends on font availability. Export review does not establish scientific correctness."]}
    report.update(export_files(svg,png,pdf))
    if png: report["exports"].append(verify_png(png))
    if pdf: report["exports"].append(verify_pdf(pdf))
    report["generated_files"]=[str(p) for p in (svg,png,pdf) if p]
    if args.report: dump_json(args.report,report)
    print(json.dumps(report,ensure_ascii=False)); return 0

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__); sub=p.add_subparsers(dest="command",required=True)
    b=sub.add_parser("build"); b.add_argument("--spec",required=True); b.add_argument("--output-dir",required=True); b.add_argument("--basename",default="figure"); b.set_defaults(func=build_command)
    e=sub.add_parser("export"); e.add_argument("--svg",required=True); e.add_argument("--output-dir",required=True); e.add_argument("--png"); e.add_argument("--pdf"); e.add_argument("--report"); e.set_defaults(func=export_command)
    v=sub.add_parser("verify"); v.add_argument("--svg",required=True); v.add_argument("--output-dir",required=True); v.add_argument("--report",required=True); v.set_defaults(func=export_command)
    args=p.parse_args(argv)
    try: return args.func(args)
    except (StudioError,OSError,ET.ParseError) as e:
        print(f"ERROR: {e}",file=sys.stderr); return 2
if __name__=="__main__": raise SystemExit(main())
