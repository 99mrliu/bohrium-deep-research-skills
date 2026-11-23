#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compile_figure.py — 声明式图稿 spec(JSON DSL) → 可编辑 SVG 编译器（纯 Python 标准库）。

用法:
    python3 compile_figure.py figure_spec.json \
        [--svg figure.svg] [--log render_log.json] [--check-determinism]

特性:
  * 最长路径分层；DFS 检测回边，回边/跨层边经底部通道绕行（回流样式 + 反向箭头）
  * 端口式正交(Manhattan)连线；间隙通道分配避免平行连线重叠
  * 图例由 styles.flow_types 与实际使用的节点类型“按构造”生成，永不与图不一致
  * 画布 auto-fit；固定画布溢出时统一等比缩小并在 render_log.json 记录比例
  * 探测 CJK 字体（fc-list + 常见路径），写入 font-family fallback 链；缺失仅告警
  * 全程排序迭代 + 两位小数定圆，同一 spec → 字节级一致 SVG（可 diff 验证）
"""
import argparse
import glob
import hashlib
import heapq
import json
import os
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape, quoteattr

PX_PER_MM = 96.0 / 25.4
MM_PER_PX = 25.4 / 96.0

MARGIN = 28.0
COL_GAP = 60.0
ROW_GAP = 26.0
LANE_GAP = 34.0
PAD_X = 14.0
PAD_Y = 10.0
FS_LABEL = 13.0
FS_SUB = 10.5
FS_TITLE = 18.0
FS_LEGEND = 10.5
FS_EDGE = 10.0
PORT_SPACING = 12.0
CHANNEL_SPACING = 8.0
DETOUR_TOP_GAP = 20.0
DETOUR_SPACING = 14.0
DETOUR_BOTTOM_GAP = 10.0
LEGEND_TOP_GAP = 24.0

DEFAULT_FLOW_TYPES = {
    "material":    {"stroke": "#1565c0", "dash": "",    "width": 1.8, "color": "#1565c0"},
    "energy":      {"stroke": "#e65100", "dash": "7 3", "width": 1.6, "color": "#e65100"},
    "information": {"stroke": "#2e7d32", "dash": "2 3", "width": 1.3, "color": "#2e7d32"},
}
DEFAULT_PALETTE = {
    "node_fill": "#ffffff", "node_stroke": "#37474f", "text": "#212121",
    "background": "#ffffff", "title": "#1a237e", "subtext": "#616161",
    "badge_fill": "#1565c0", "note_fill": "#fffde7",
    "lane_fills": ["#eceff1", "#e3f2fd", "#e8f5e9", "#fff3e0", "#f3e5f5"],
}
NODE_KINDS = ("unit", "step", "stage", "data", "note")
KIND_LABEL = {"unit": "装置单元", "step": "步骤", "stage": "阶段",
              "data": "数据/储罐", "note": "注释"}
BACKFLOW_DASH = "5 3"

sys.setrecursionlimit(20000)


def fmt(x):
    """两位小数定圆；消除 -0.00。"""
    v = round(float(x), 2)
    if abs(v) < 0.005:
        v = 0.0
    return "%.2f" % v


def est_text_width(s, size):
    """估算文本宽度（px）：CJK 全宽，ASCII 半宽。"""
    w = 0.0
    for ch in s:
        o = ord(ch)
        if o >= 0x2E80 or o in (0x2014, 0x2018, 0x2019, 0x201C, 0x201D):
            w += size
        elif ch == " ":
            w += size * 0.32
        else:
            w += size * 0.56
    return w


def node_dims(nd):
    kind = nd.get("kind", "unit")
    w = est_text_width(nd.get("label", "?"), FS_LABEL) + 2 * PAD_X
    sub = nd.get("sublabel", "")
    if sub:
        w = max(w, est_text_width(sub, FS_SUB) + 2 * PAD_X)
    for p in nd.get("parts", []):
        w = max(w, est_text_width(p, FS_SUB) + 2 * PAD_X)
    h = 2 * PAD_Y + 18.0
    if sub:
        h += 14.0
    h += 16.0 * len(nd.get("parts", []))
    if kind == "data":
        w += 24.0
    if kind == "step":
        w = max(w, 88.0)
        h = max(h, 48.0)
    if kind == "stage":
        w += 28.0
    return max(w, 72.0), max(h, 42.0)


# ---------------------------------------------------------------- 图结构 ----
def _tarjan_sccs(ids, adj):
    """Tarjan 强连通分量（递归，图规模小）。确定性：按 id 序遍历。"""
    index, low, onstack, stack, sccs = {}, {}, set(), [], []
    counter = [0]

    def strongconnect(v):
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack.add(v)
        for _eid, _idx, w in adj[v]:
            if w not in index:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in onstack:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            scc = []
            while True:
                w = stack.pop()
                onstack.discard(w)
                scc.append(w)
                if w == v:
                    break
            sccs.append(sorted(scc))

    for v in sorted(ids):
        if v not in index:
            strongconnect(v)
    return sccs


def find_back_edges(ids, edges):
    """反馈边检测：SCC 内做 DFS，指向灰色祖先的边记为回边，移除后迭代至无环。

    跨 SCC 的边永不误判（缩点是 DAG），因此只有真正处于环上的边
    （如循环物料/回流信号）会被选为回边。确定性：入口与邻接均排序。
    返回回边的下标集合。
    """
    full = {i: [] for i in ids}
    for idx, e in enumerate(edges):
        if e["from"] in full and e["to"] in full and e["from"] != e["to"]:
            full[e["from"]].append((e["_eid"], idx, e["to"]))
    for u in full:
        full[u].sort(key=lambda t: t[0])

    back = set()
    for _ in range(len(edges) + 1):  # 每轮至少消去一条边，必有穷
        adj = {i: [t for t in full[i] if t[1] not in back] for i in ids}
        sccs = [s for s in _tarjan_sccs(ids, adj) if len(s) > 1]
        if not sccs:
            break
        for scc in sccs:
            sset = set(scc)
            # SCC 入口节点：有来自 SCC 外的入边；按(最小外部入边 eid, id)排序
            ext_in = {}
            for n in scc:
                for u in ids:
                    for eid, idx, v in adj[u]:
                        if v == n and u not in sset:
                            ext_in.setdefault(n, []).append(eid)
            entries = sorted(scc,
                             key=lambda n: (min(ext_in.get(n, ["~"])), n))
            color = {n: 0 for n in scc}

            def dfs(u):
                color[u] = 1
                for _eid, idx, v in adj[u]:
                    if v not in sset:
                        continue
                    if color[v] == 1:
                        back.add(idx)
                    elif color[v] == 0:
                        dfs(v)
                color[u] = 2

            for s in entries:
                if color[s] == 0:
                    dfs(s)
    return back


def compute_layers(ids, edges, back, warnings):
    """非回边构成 DAG；Kahn 拓扑序 + 最长路径分层。"""
    preds = {i: [] for i in ids}
    succs = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for idx, e in enumerate(edges):
        if idx in back or e["from"] not in preds or e["to"] not in preds:
            continue
        preds[e["to"]].append(e["from"])
        succs[e["from"]].append(e["to"])
        indeg[e["to"]] += 1
    heap = [i for i in ids if indeg[i] == 0]
    heapq.heapify(heap)
    layer = {}
    while heap:
        u = heapq.heappop(heap)
        layer[u] = 0 if not preds[u] else max(layer[p] for p in preds[u]) + 1
        for v in succs[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                heapq.heappush(heap, v)
    for i in ids:
        if i not in layer:
            layer[i] = 0
            warnings.append("节点 %s 分层失败（残留环？），置于第 0 层" % i)
    return layer, preds, succs


def order_layers(ids, layer, edges, back):
    """层内排序：初始按 id，两轮重心(barycenter)扫描减少交叉，id 兜底保证确定性。"""
    layers = {}
    for i in ids:
        layers.setdefault(layer[i], []).append(i)
    for l in layers:
        layers[l].sort()
    pos = {i: k for l in layers for k, i in enumerate(layers[l])}
    fwd = [(e["from"], e["to"]) for i, e in enumerate(edges) if i not in back]
    for _ in range(2):
        for direction in ("down", "up"):
            ls = sorted(layers) if direction == "down" else sorted(layers, reverse=True)
            for l in ls:
                bary = {}
                for nid in layers[l]:
                    nb = [p for p, v in fwd if v == nid] if direction == "down" \
                        else [v for p, v in fwd if p == nid]
                    nb = [x for x in nb if (layer[x] < l if direction == "down"
                                            else layer[x] > l)]
                    bary[nid] = (sum(pos[x] for x in nb) / len(nb)
                                 if nb else pos[nid])
                layers[l].sort(key=lambda n: (bary[n], n))
            for k, nid in enumerate(layers[l]):
                pos[nid] = k
    return layers


# ---------------------------------------------------------------- 字体 ----
def detect_cjk_fonts():
    """探测可用 CJK 字体：fc-list（如存在）+ 常见路径探测。"""
    detected = set()
    exe = shutil.which("fc-list")
    if exe:
        try:
            out = subprocess.run([exe, ":", "lang=zh", "family"],
                                 capture_output=True, text=True, timeout=10)
            for line in out.stdout.splitlines():
                for fam in line.split(","):
                    fam = fam.strip()
                    if fam:
                        detected.add(fam)
        except Exception:
            pass
    probes = [
        ("/System/Library/Fonts/PingFang.ttc", "PingFang SC"),
        ("/System/Library/Fonts/Hiragino Sans GB.ttc", "Hiragino Sans GB"),
        ("/System/Library/Fonts/STHeiti Light.ttc", "Heiti SC"),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "Noto Sans CJK SC"),
        ("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", "WenQuanYi Micro Hei"),
        ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", "WenQuanYi Zen Hei"),
    ]
    for pat, fam in probes:
        if os.path.exists(pat):
            detected.add(fam)
    for pat, fam in [("/usr/share/fonts/**/NotoSansCJK*", "Noto Sans CJK SC"),
                     ("/usr/share/fonts/**/wqy*", "WenQuanYi Micro Hei"),
                     ("/usr/share/fonts/**/*Noto*CJK*", "Noto Sans CJK SC")]:
        if glob.glob(pat, recursive=True):
            detected.add(fam)
    preferred = ["PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC",
                 "Source Han Sans SC", "WenQuanYi Micro Hei", "Heiti SC",
                 "Microsoft YaHei", "SimHei"]
    chain = [f for f in preferred if f in detected]
    chain += [f for f in preferred if f not in chain]  # 未探测到的仍作 fallback
    chain.append("sans-serif")
    warning = None
    if not detected:
        warning = ("未探测到任何 CJK 字体（无 fc-list 且常见路径不存在），"
                   "中文可能显示为豆腐块(tofu)；SVG 仍已写入完整 fallback 链。")
    return sorted(detected), chain, warning


# ---------------------------------------------------------------- 编译 ----
def compile_spec(spec):
    warnings = []
    kind = spec.get("kind", "stepflow")
    styles = spec.get("styles") or {}
    flow_types = dict(DEFAULT_FLOW_TYPES)
    for k, v in (styles.get("flow_types") or {}).items():
        base = dict(DEFAULT_FLOW_TYPES.get(k, DEFAULT_FLOW_TYPES["material"]))
        base.update(v)
        flow_types[k] = base
    palette = dict(DEFAULT_PALETTE)
    palette.update(styles.get("palette") or {})

    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    stages = spec.get("stages") or []
    for i, e in enumerate(edges):
        e["_eid"] = e.get("id") or "e%02d" % i
        if not e.get("flow_type"):
            e["flow_type"] = "material"
            warnings.append("边 %s 缺少 flow_type，按 material 处理" % e["_eid"])
        elif e["flow_type"] not in flow_types:
            warnings.append("边 %s 的 flow_type '%s' 未定义，按 material 渲染"
                            % (e["_eid"], e["flow_type"]))
    ids = [n["id"] for n in nodes]
    node_by_id = {n["id"]: n for n in nodes}

    # ---- 分层 / 排序 ----
    back = find_back_edges(ids, edges)
    layer, preds, succs = compute_layers(ids, edges, back, warnings)
    layers = order_layers(ids, layer, edges, back)
    max_layer = max(layers) if layers else 0

    dims = {n["id"]: node_dims(n) for n in nodes}
    col_w = {}
    for l in range(max_layer + 1):
        col_w[l] = max([dims[i][0] for i in layers.get(l, [])] or [72.0])
    col_x = {}
    x = MARGIN
    for l in range(max_layer + 1):
        col_x[l] = x
        x += col_w[l] + COL_GAP
    band_w = x - COL_GAP - MARGIN

    # ---- y 坐标：普通 = 单列垂直居中；roadmap = 泳道 ----
    pos = {}  # id -> (x, y, w, h)
    is_roadmap = (kind == "roadmap")
    lanes = []  # (stage_id, label, y, h)
    if is_roadmap:
        stage_ids = [s.get("id") for s in stages]
        lane_of = {}
        for n in nodes:
            lane_of[n["id"]] = n.get("stage") or (stage_ids[0] if stage_ids else None)
        stacks = {}
        for l in range(max_layer + 1):
            for nid in layers.get(l, []):
                stacks.setdefault((lane_of[nid], l), []).append(nid)
        y = 0.0
        lane_y = {}
        for si, s in enumerate(stages):
            sid = s.get("id")
            row_h = max([sum(dims[i][1] for i in st) + ROW_GAP * (len(st) - 1)
                         for (stid, l), st in stacks.items() if stid == sid] or [60.0])
            lane_y[sid] = (y, row_h)
            lanes.append((sid, s.get("label", sid), y, row_h))
            y += row_h + LANE_GAP
        band_h = max(y - LANE_GAP, 60.0)
        for (sid, l), st in sorted(stacks.items()):
            ry, rh = lane_y[sid]
            sh = sum(dims[i][1] for i in st) + ROW_GAP * (len(st) - 1)
            yy = ry + (rh - sh) / 2.0
            for nid in st:
                w, h = dims[nid]
                pos[nid] = (col_x[l], yy, w, h)
                yy += h + ROW_GAP
    else:
        col_h = {}
        for l in range(max_layer + 1):
            st = layers.get(l, [])
            col_h[l] = sum(dims[i][1] for i in st) + ROW_GAP * max(len(st) - 1, 0)
        band_h = max(col_w and col_h.values() or [60.0])
        for l in range(max_layer + 1):
            yy = (band_h - col_h[l]) / 2.0
            for nid in layers.get(l, []):
                w, h = dims[nid]
                pos[nid] = (col_x[l], yy, w, h)
                yy += h + ROW_GAP

    content_w = band_w + 2 * MARGIN

    # ---- 边分类 ----
    detour = []  # 底部绕行（回边 + 跨层前向边）
    adjacent = []
    for idx, e in enumerate(edges):
        u, v = e["from"], e["to"]
        if u not in pos or v not in pos:
            warnings.append("边 %s 端点缺失，已跳过" % e["_eid"])
            continue
        if idx in back or layer[v] != layer[u] + 1:
            detour.append(idx)
        else:
            adjacent.append(idx)
    detour.sort(key=lambda i: edges[i]["_eid"])

    # ---- 端口分配 ----
    out_fwd = {i: [] for i in ids}
    in_fwd = {i: [] for i in ids}
    bot = {i: [] for i in ids}
    for idx in adjacent:
        e = edges[idx]
        out_fwd[e["from"]].append(idx)
        in_fwd[e["to"]].append(idx)
    for idx in detour:
        e = edges[idx]
        bot[e["from"]].append(idx)
        bot[e["to"]].append(idx)
    for nid in ids:
        out_fwd[nid].sort(key=lambda i: (pos[edges[i]["to"]][1], edges[i]["_eid"]))
        in_fwd[nid].sort(key=lambda i: (pos[edges[i]["from"]][1], edges[i]["_eid"]))
        bot[nid].sort(key=lambda i: edges[i]["_eid"])

    def port_y(nid, lst, idx):
        k = lst.index(idx)
        x0, y0, w, h = pos[nid]
        cy = y0 + h / 2.0
        off = (k - (len(lst) - 1) / 2.0) * PORT_SPACING
        return min(max(cy + off, y0 + 8.0), y0 + h - 8.0)

    def bot_x(nid, idx):
        k = bot[nid].index(idx)
        x0, y0, w, h = pos[nid]
        return x0 + w / 2.0 + (k - (len(bot[nid]) - 1) / 2.0) * PORT_SPACING

    # ---- 间隙通道（前向相邻边）----
    gap_of = {}
    for idx in adjacent:
        gap_of.setdefault(layer[edges[idx]["from"]], []).append(idx)
    gap_midx = {}
    for g, lst in gap_of.items():
        lst.sort(key=lambda i: edges[i]["_eid"])
        center = col_x[g] + col_w[g] + COL_GAP / 2.0
        for k, idx in enumerate(lst):
            gap_midx[idx] = center + (k - (len(lst) - 1) / 2.0) * CHANNEL_SPACING

    # ---- 底部绕行通道 ----
    title_h = FS_TITLE + 34.0
    band_top = title_h
    detour_top = band_top + band_h + DETOUR_TOP_GAP
    chan_y = {}
    for k, idx in enumerate(detour):
        chan_y[idx] = detour_top + k * DETOUR_SPACING
    detour_bottom = (detour_top + (len(detour) - 1) * DETOUR_SPACING
                     + DETOUR_BOTTOM_GAP) if detour else band_top + band_h

    # ---- 图例（按构造：与实际使用的样式同源）----
    used_flow = sorted({e["flow_type"] for e in edges})
    used_kinds = sorted({n.get("kind", "unit") for n in nodes})
    legend_entries = []
    for ft in used_flow:
        legend_entries.append({"type": "flow", "name": ft, "style": flow_types[ft]})
    for kd in used_kinds:
        legend_entries.append({"type": "kind", "name": kd})
    if back:
        legend_entries.append({"type": "backflow", "name": "backflow"})
    # 换行排版
    legend_w = content_w - 2 * MARGIN - 24.0
    lx, ly = 12.0, 30.0
    row_h = 22.0
    placed = []
    for ent in legend_entries:
        label = ent["name"] if ent["type"] == "flow" else (
            "回流边(底部绕行)" if ent["type"] == "backflow" else KIND_LABEL.get(ent["name"], ent["name"]))
        ent["_label"] = label
        ew = 40.0 + est_text_width(label, FS_LEGEND) + 20.0
        if lx + ew > legend_w and placed:
            lx = 12.0
            ly += row_h
        ent["_x"], ent["_y"], ent["_w"] = lx, ly, ew
        placed.append(ent)
        lx += ew
    legend_h = ly + row_h + 8.0
    legend_top = detour_bottom + LEGEND_TOP_GAP

    content_h = legend_top + legend_h + MARGIN

    # ---- 画布 ----
    canvas = spec.get("canvas", "auto")
    fixed = isinstance(canvas, dict) and canvas.get("width_mm") and canvas.get("height_mm")
    if fixed:
        W = canvas["width_mm"] * PX_PER_MM
        H = canvas["height_mm"] * PX_PER_MM
        scale = min(1.0, W / content_w, H / content_h)
        tx = (W - content_w * scale) / 2.0
        ty = (H - content_h * scale) / 2.0
        canvas_mm = {"width_mm": round(canvas["width_mm"], 2),
                     "height_mm": round(canvas["height_mm"], 2), "mode": "fixed"}
        if scale < 1.0:
            warnings.append("固定画布溢出，已等比缩放至 %.3f" % scale)
    else:
        W, H = content_w, content_h
        scale, tx, ty = 1.0, 0.0, 0.0
        canvas_mm = {"width_mm": round(W * MM_PER_PX, 2),
                     "height_mm": round(H * MM_PER_PX, 2), "mode": "auto"}

    # ---- 字体 ----
    detected, font_chain, font_warn = detect_cjk_fonts()
    if font_warn:
        warnings.append(font_warn)
    font_family = ",".join("'%s'" % f if " " in f else f for f in font_chain)

    # ===============================  发射 SVG  ===============================
    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<svg xmlns="http://www.w3.org/2000/svg" '
               'width="%smm" height="%smm" viewBox="0 0 %s %s" '
               'font-family="%s">' % (
                   fmt(canvas_mm["width_mm"]), fmt(canvas_mm["height_mm"]),
                   fmt(W), fmt(H), escape(font_family)))
    # defs: 每种实际使用的 flow_type 一个箭头 marker
    out.append("  <defs>")
    for ft in used_flow:
        st = flow_types[ft]
        out.append('    <marker id="arrow-%s" viewBox="0 0 10 10" refX="9" refY="5" '
                   'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                   '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>'
                   % (escape(ft), escape(st["stroke"])))
    out.append("  </defs>")
    out.append('  <rect id="background" x="0" y="0" width="%s" height="%s" fill="%s"/>'
               % (fmt(W), fmt(H), escape(palette["background"])))

    def g_open(gid):
        out.append('  <g id=%s>' % quoteattr(gid))

    transform = 'transform="translate(%s,%s) scale(%s)"' % (fmt(tx), fmt(ty), fmt(scale)) \
        if (tx or ty or scale != 1.0) else ""

    # 标题层（不随内容缩放）
    g_open("layer-title")
    title = spec.get("title", "")
    out.append('    <text id="title" x="%s" y="%s" text-anchor="middle" '
               'font-size="%s" font-weight="bold" fill="%s">%s</text>'
               % (fmt(W / 2.0), fmt(MARGIN - 4.0), fmt(FS_TITLE),
                  escape(palette["title"]), escape(title)))
    out.append("  </g>")

    out.append('  <g id="layer-content" %s>' % transform if transform
               else '  <g id="layer-content">')

    # 泳道层（roadmap）
    if is_roadmap and lanes:
        g_open("layer-stages")
        fills = palette["lane_fills"]
        for si, (sid, label, ry, rh) in enumerate(lanes):
            y0 = band_top + ry
            tip = 18.0
            pts = [(MARGIN, y0), (MARGIN + band_w - tip, y0),
                   (MARGIN + band_w, y0 + rh / 2.0),
                   (MARGIN + band_w - tip, y0 + rh), (MARGIN, y0 + rh)]
            out.append('    <g id="stage-%s" data-eid=%s>' % (escape(str(sid)), quoteattr(str(sid))))
            out.append('      <polygon points="%s" fill="%s" stroke="#b0bec5" '
                       'stroke-width="1"/>'
                       % (" ".join("%s,%s" % (fmt(px), fmt(py)) for px, py in pts),
                          escape(fills[si % len(fills)])))
            # 泳道名置于泳道上方空隙，避免被首列节点遮挡
            out.append('      <text x="%s" y="%s" font-size="%s" font-weight="bold" '
                       'fill="%s">%s</text>'
                       % (fmt(MARGIN + 4.0), fmt(y0 - 8.0), fmt(FS_SUB),
                          escape(palette["subtext"]), escape(label)))
            out.append("    </g>")
        out.append("  </g>")

    # 连线层
    g_open("layer-edges")
    for idx, e in enumerate(edges):
        if e["from"] not in pos or e["to"] not in pos:
            continue
        ft = e["flow_type"]
        st = flow_types[ft]
        u, v = e["from"], e["to"]
        ux, uy, uw, uh = pos[u]
        vx, vy, vw, vh = pos[v]
        is_back = idx in back
        dash = st["dash"]
        if is_back and not dash:
            dash = BACKFLOW_DASH
        if idx in gap_midx:  # 前向相邻：右端口 → 间隙通道 → 左端口
            x1, y1 = ux + uw, port_y(u, out_fwd[u], idx)
            x2, y2 = vx, port_y(v, in_fwd[v], idx)
            mx = gap_midx[idx]
            d = "M%s,%s L%s,%s L%s,%s L%s,%s" % (fmt(x1), fmt(band_top + y1),
                                                 fmt(mx), fmt(band_top + y1),
                                                 fmt(mx), fmt(band_top + y2),
                                                 fmt(x2), fmt(band_top + y2))
            lx_, ly_ = mx, band_top + (y1 + y2) / 2.0 - 4.0
        else:  # 底部绕行（回边自右向左，跨层前向自左向右）
            # 出/入均先下 7px 再水平 jog 到列间隙中的垂直通道，避免穿越
            # 同列下方节点的包围盒（间隙中不会有节点）。
            JOG = 7.0
            x1 = bot_x(u, idx)
            x2 = bot_x(v, idx)
            by1 = band_top + uy + uh
            by2 = band_top + vy + vh
            cy = chan_y[idx]
            gap_off = 10.0 + (detour.index(idx) % 5) * 6.0
            lu, lv = layer[u], layer[v]
            if lu <= lv:  # 前向跨层：右侧间隙下降
                drop_x = col_x[lu] + col_w[lu] + gap_off
                rise_x = col_x[lv] - gap_off
            else:  # 回边：左侧间隙下降
                drop_x = col_x[lu] - gap_off
                rise_x = col_x[lv] - gap_off
            if abs(drop_x - rise_x) < 4.0:
                rise_x = drop_x - 9.0
            d = "M%s,%s L%s,%s L%s,%s L%s,%s L%s,%s L%s,%s L%s,%s L%s,%s" % (
                fmt(x1), fmt(by1),
                fmt(x1), fmt(by1 + JOG),
                fmt(drop_x), fmt(by1 + JOG),
                fmt(drop_x), fmt(cy),
                fmt(rise_x), fmt(cy),
                fmt(rise_x), fmt(by2 + JOG),
                fmt(x2), fmt(by2 + JOG),
                fmt(x2), fmt(by2))
            lx_, ly_ = (drop_x + rise_x) / 2.0, cy - 5.0
        out.append('    <g id="edge-%s" data-eid=%s data-from=%s data-to=%s '
                   'data-flow=%s data-backflow="%s">' % (
                       escape(e["_eid"]), quoteattr(e["_eid"]), quoteattr(u),
                       quoteattr(v), quoteattr(ft),
                       "true" if is_back else "false"))
        out.append('      <path d="%s" fill="none" stroke="%s" stroke-width="%s"%s '
                   'marker-end="url(#arrow-%s)"/>' % (
                       d, escape(st["stroke"]), fmt(st["width"]),
                       ' stroke-dasharray="%s"' % escape(dash) if dash else "",
                       escape(ft)))
        if e.get("label"):
            out.append('      <text x="%s" y="%s" text-anchor="middle" font-size="%s" '
                       'fill="%s" stroke="#ffffff" stroke-width="3" '
                       'paint-order="stroke">%s</text>'
                       % (fmt(lx_), fmt(ly_), fmt(FS_EDGE),
                          escape(st.get("color", st["stroke"])), escape(e["label"])))
        out.append("    </g>")
    out.append("  </g>")

    # 节点层
    g_open("layer-nodes")
    for n in nodes:
        nid = n["id"]
        if nid not in pos:
            continue
        x0, y0, w, h = pos[nid]
        y0 += band_top
        kd = n.get("kind", "unit")
        out.append('    <g id="node-%s" data-eid=%s data-kind=%s '
                   'transform="translate(%s,%s)">'
                   % (escape(nid), quoteattr(nid), quoteattr(kd), fmt(x0), fmt(y0)))
        fill, stroke = palette["node_fill"], palette["node_stroke"]
        if kd == "unit":
            out.append('      <rect x="0" y="0" width="%s" height="%s" rx="8" '
                       'fill="%s" stroke="%s" stroke-width="1.5"/>'
                       % (fmt(w), fmt(h), fill, stroke))
        elif kd == "step":
            out.append('      <rect x="0" y="0" width="%s" height="%s" rx="4" '
                       'fill="%s" stroke="%s" stroke-width="1.5"/>'
                       % (fmt(w), fmt(h), fill, stroke))
            num = n.get("num", "")
            out.append('      <circle cx="16" cy="16" r="11" fill="%s"/>'
                       % escape(palette["badge_fill"]))
            out.append('      <text x="16" y="20.5" text-anchor="middle" '
                       'font-size="11" font-weight="bold" fill="#ffffff">%s</text>'
                       % escape(str(num)))
        elif kd == "stage":
            t = 14.0
            pts = [(0, 0), (w - t, 0), (w, h / 2.0), (w - t, h), (0, h), (t, h / 2.0)]
            out.append('      <polygon points="%s" fill="%s" stroke="%s" '
                       'stroke-width="1.5"/>'
                       % (" ".join("%s,%s" % (fmt(px), fmt(py)) for px, py in pts),
                          fill, stroke))
        elif kd == "data":
            s = 12.0
            pts = [(s, 0), (w, 0), (w - s, h), (0, h)]
            out.append('      <polygon points="%s" fill="%s" stroke="%s" '
                       'stroke-width="1.5"/>'
                       % (" ".join("%s,%s" % (fmt(px), fmt(py)) for px, py in pts),
                          fill, stroke))
        else:  # note
            out.append('      <rect x="0" y="0" width="%s" height="%s" rx="4" '
                       'fill="%s" stroke="%s" stroke-width="1.2" '
                       'stroke-dasharray="4 3"/>' % (fmt(w), fmt(h),
                                                     palette["note_fill"], stroke))
        # 文本（step 节点右移避开左上角编号徽章）
        cx = w / 2.0 + (10.0 if kd == "step" else 0.0)
        yy = PAD_Y + 13.0
        if kd == "step":
            yy = h / 2.0 - (2.0 if n.get("sublabel") else -4.0)
        out.append('      <text x="%s" y="%s" text-anchor="middle" font-size="%s" '
                   'font-weight="bold" fill="%s">%s</text>'
                   % (fmt(cx), fmt(yy), fmt(FS_LABEL), escape(palette["text"]),
                      escape(n.get("label", ""))))
        yy += 15.0
        if n.get("sublabel"):
            out.append('      <text x="%s" y="%s" text-anchor="middle" font-size="%s" '
                       'fill="%s">%s</text>'
                       % (fmt(cx), fmt(yy), fmt(FS_SUB),
                          escape(palette["subtext"]), escape(n["sublabel"])))
            yy += 4.0
        for p in n.get("parts", []):
            yy += 12.0
            out.append('      <line x1="8" y1="%s" x2="%s" y2="%s" stroke="%s" '
                       'stroke-width="0.75"/>' % (fmt(yy - 8.0), fmt(w - 8),
                                                   fmt(yy - 8.0), stroke))
            out.append('      <text x="%s" y="%s" text-anchor="middle" font-size="%s" '
                       'fill="%s">%s</text>'
                       % (fmt(cx), fmt(yy + 1.0), fmt(FS_SUB),
                          escape(palette["subtext"]), escape(p)))
            yy += 4.0
        out.append("    </g>")
    out.append("  </g>")

    # 图例层
    g_open("layer-legend")
    out.append('    <rect x="%s" y="%s" width="%s" height="%s" rx="6" fill="#ffffff" '
               'stroke="#cfd8dc" stroke-width="1"/>'
               % (fmt(MARGIN), fmt(legend_top), fmt(content_w - 2 * MARGIN),
                  fmt(legend_h)))
    out.append('    <text x="%s" y="%s" font-size="%s" font-weight="bold" '
               'fill="%s">图例</text>'
               % (fmt(MARGIN + 12.0), fmt(legend_top + 18.0), fmt(FS_LEGEND),
                  escape(palette["text"])))
    for ent in placed:
        ex = MARGIN + 12.0 + ent["_x"]
        ey = legend_top + ent["_y"] + 4.0
        label = ent["_label"]
        if ent["type"] == "flow":
            st = ent["style"]
            dash = st["dash"] or (BACKFLOW_DASH if ent["name"] == "backflow" else "")
            out.append('    <line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" '
                       'stroke-width="%s"%s marker-end="url(#arrow-%s)"/>'
                       % (fmt(ex), fmt(ey), fmt(ex + 32.0), fmt(ey),
                          escape(st["stroke"]), fmt(st["width"]),
                          ' stroke-dasharray="%s"' % escape(st["dash"]) if st["dash"] else "",
                          escape(ent["name"])))
        elif ent["type"] == "backflow":
            st = flow_types.get("material", DEFAULT_FLOW_TYPES["material"])
            out.append('    <line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" '
                       'stroke-width="%s" stroke-dasharray="%s"/>'
                       % (fmt(ex), fmt(ey), fmt(ex + 32.0), fmt(ey),
                          escape(st["stroke"]), fmt(st["width"]), BACKFLOW_DASH))
        else:  # node kind 小样例
            kd = ent["name"]
            if kd == "data":
                out.append('    <polygon points="%s" fill="%s" stroke="%s"/>'
                           % (" ".join("%s,%s" % (fmt(a), fmt(b)) for a, b in
                                       [(ex + 4, ey - 6), (ex + 28, ey - 6),
                                        (ex + 24, ey + 6), (ex, ey + 6)]),
                              palette["node_fill"], palette["node_stroke"]))
            elif kd == "note":
                out.append('    <rect x="%s" y="%s" width="28" height="12" rx="2" '
                           'fill="%s" stroke="%s" stroke-dasharray="3 2"/>'
                           % (fmt(ex), fmt(ey - 6), palette["note_fill"],
                              palette["node_stroke"]))
            elif kd == "stage":
                out.append('    <polygon points="%s" fill="%s" stroke="%s"/>'
                           % (" ".join("%s,%s" % (fmt(a), fmt(b)) for a, b in
                                       [(ex, ey - 6), (ex + 22, ey - 6), (ex + 28, ey),
                                        (ex + 22, ey + 6), (ex, ey + 6), (ex + 6, ey)]),
                              palette["node_fill"], palette["node_stroke"]))
            else:
                out.append('    <rect x="%s" y="%s" width="28" height="12" rx="%s" '
                           'fill="%s" stroke="%s"/>'
                           % (fmt(ex), fmt(ey - 6), "4" if kd == "step" else "3",
                              palette["node_fill"], palette["node_stroke"]))
        out.append('    <text x="%s" y="%s" font-size="%s" fill="%s">%s</text>'
                   % (fmt(ex + 38.0), fmt(ey + 4.0), fmt(FS_LEGEND),
                      escape(palette["text"]), escape(label)))
    out.append("  </g>")

    out.append("  </g>")  # layer-content
    out.append("</svg>")
    svg = "\n".join(out) + "\n"

    log = {
        "kind": kind,
        "title": title,
        "canvas": canvas_mm,
        "scale": round(scale, 4),
        "counts": {"nodes": len(nodes), "edges": len(edges),
                   "layers": max_layer + 1, "lanes": len(lanes)},
        "back_edges": sorted(edges[i]["_eid"] for i in back),
        "detour_edges": [edges[i]["_eid"] for i in detour],
        "legend_entries": [e["_label"] for e in placed],
        "flow_types_used": used_flow,
        "node_kinds_used": used_kinds,
        "font_chain": font_chain,
        "fonts_detected": detected,
        "warnings": warnings,
        "svg_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
    }
    return svg, log


def main(argv):
    ap = argparse.ArgumentParser(description="编译 figure_spec.json → 可编辑 SVG")
    ap.add_argument("spec")
    ap.add_argument("--svg", default="figure.svg")
    ap.add_argument("--log", default="render_log.json")
    ap.add_argument("--check-determinism", action="store_true",
                    help="同进程渲染两次并比较字节；仍建议外部两次运行后 diff")
    args = ap.parse_args(argv[1:])

    with open(args.spec, "r", encoding="utf-8") as f:
        spec = json.load(f)
    spec_hash = hashlib.sha256(
        json.dumps(spec, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    svg, log = compile_spec(spec)
    log["spec_sha256"] = spec_hash
    if args.check_determinism:
        svg2, _ = compile_spec(json.loads(json.dumps(spec)))
        log["determinism"] = {"checked": True,
                              "identical": svg == svg2,
                              "method": "in-process double render; "
                                        "跨进程请再运行一次并 diff SVG"}
    else:
        log["determinism"] = {"checked": False}

    with open(args.svg, "w", encoding="utf-8", newline="\n") as f:
        f.write(svg)
    with open(args.log, "w", encoding="utf-8", newline="\n") as f:
        json.dump(log, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("[compile_figure] %s -> %s (%smm x %smm, scale=%.3f, warnings=%d)"
          % (args.spec, args.svg, log["canvas"]["width_mm"],
             log["canvas"]["height_mm"], log["scale"], len(log["warnings"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
