#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qc_figure.py — Figure IR + SVG 自动质检器（纯标准库）。

缺陷分类学与修复动作见 references/failure-taxonomy.md。每个缺陷：
  {"code", "severity": "error"|"warn", "element", "evidence", "suggested_fix"}

用法:
  python3 qc_figure.py figure_ir.json figure.svg <source_dir> --report qc_report.json
      [--round N] [--export-pdf fig.pdf] [--export-png fig.png]

检测器（10 个代码）:
  DANGLING_EDGE        边端点 id 不在 IR nodes（IR 级）+ 箭头端点几何上未触及任何节点盒（SVG 级）
  REVERSED_FLOW        顺序语义边 from.order >= to.order；及箭头方向与声明顺序相反
  NUMBERING_GAP        有序步骤编号不是 S1..Sn 连续序列；与源文本枚举步数不符
  LABEL_SOURCE_MISMATCH 节点标签词元在源文本中找不到（warn；允许合理缩写）
  LEGEND_MISMATCH      图例色块/线型与边上实际使用的颜色/虚线不一致（解析 SVG 样式）
  TEXT_OVERFLOW        标签估算宽度（CJK 1.0em / ASCII 0.55em）超过盒宽（>盒宽 error，>90% warn）
  FONT_RISK            标签含 CJK 但系统无 CJK 字体（warn，给回退链建议）
  CANVAS_OVERFLOW      任何元素包围盒超出画布 viewBox
  EXPORT_FAIL          导出后 PNG/PDF 缺失 / 零字节 / 文件头不可读（需 --export-pdf/--export-png）
  UNVERIFIED_QUOTE     source.quote 在抽取文本中找不到（warn，仅记录不阻断）

退出码恒为 0；error 级缺陷数见报告 summary.errors。永不抛异常到顶层。
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

PALETTE = {
    "material":    {"color": "#1f77b4", "dash": None},
    "energy":      {"color": "#d62728", "dash": "4,2"},
    "information": {"color": "#2ca02c", "dash": "1,3"},
    "sequence":    {"color": "#666666", "dash": None},
}
TOUCH_TOL = 1.5   # 端点视为触及节点盒的容差（mm）
CANVAS_TOL = 0.6

FIX = {
    "DANGLING_EDGE": "把边的 from/to 改为 IR 中存在的节点 id；若源文本并无此连接，删除该边——禁止凭空补齐连接。",
    "REVERSED_FLOW": "材料/步骤流向反了：交换边的 from 与 to，或修正节点的 order 字段，使 order 沿流向递增。",
    "NUMBERING_GAP": "把有序节点的 order 重排为 1..n 连续整数，并与源文本步骤顺序一一对应。",
    "LABEL_SOURCE_MISMATCH": "标签用词与源文本不一致：改用源文本中的原词（或确认是合理缩写并在 uncertainties 说明）。",
    "LEGEND_MISMATCH": "删除 IR legend 中的自定义 color/dash（或删掉整个 legend 让渲染器按用到的边类型自动生成），使图例与边样式一致。",
    "TEXT_OVERFLOW": "标签超出节点盒：缩短标签用词（用源文本中的简称），或在 IR canvas 中加大画布/拆行。",
    "FONT_RISK": "系统无 CJK 字体，中文可能变方框：安装 Noto Sans CJK / 文泉驿，或依赖渲染端字体回退链，并在导出后用 PNG 目检。",
    "CANVAS_OVERFLOW": "元素超出画布：在 IR canvas 设置更大的 width_mm/height_mm，或改回 auto。",
    "EXPORT_FAIL": "导出产物缺失/损坏：查看 export_report.json 的 attempts，换回退链上的其他工具重试；实在不行仅交付 SVG 并如实声明。",
    "UNVERIFIED_QUOTE": "source.quote 与源文本对不上：从抽取文本中复制原文片段替换；仅记录不阻断。",
}


# ---------- 文本工具 ----------

def norm_ws(s):
    return re.sub(r"[\s　]+", "", s).lower()


def norm_loose(s):
    return re.sub(r"[\s　，。、；：,.;:!?？！（）()【】\[\]\"'“”‘’《》<>\-—·]+", "", s).lower()


def est_w(text, fs):
    return sum(fs if ord(c) >= 0x2E80 else fs * 0.55 for c in text)


def has_cjk(s):
    return any(ord(c) >= 0x2E80 for c in s)


def load_corpus(source_dir):
    """读取 source_dir 下所有文本材料；PDF 在 pdftotext 可用时抽取。返回 (全文, notes)。"""
    texts, notes = [], []
    if not source_dir or not os.path.isdir(source_dir):
        return "", [f"source_dir 不存在: {source_dir}"]
    for name in sorted(os.listdir(source_dir)):
        p = os.path.join(source_dir, name)
        if not os.path.isfile(p):
            continue
        low = name.lower()
        try:
            if low.endswith((".txt", ".md", ".csv", ".tsv", ".json")):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    texts.append(f.read())
            elif low.endswith(".pdf"):
                exe = shutil.which("pdftotext")
                if exe:
                    r = subprocess.run([exe, "-layout", p, "-"],
                                       capture_output=True, timeout=180)
                    texts.append(r.stdout.decode("utf-8", "ignore"))
                else:
                    notes.append(f"跳过 PDF（pdftotext 不可用）: {name}")
        except Exception as exc:
            notes.append(f"读取失败 {name}: {exc}")
    if not texts:
        notes.append("源文本为空：LABEL_SOURCE_MISMATCH / UNVERIFIED_QUOTE / 步数核对被跳过")
    return "\n".join(texts), notes


# ---------- SVG 解析 ----------

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _norm_dash(d):
    if d is None:
        return None
    d = d.strip().replace(" ", "")
    return None if d in ("", "none") else d


PATH_NUM = re.compile(r"(-?\d+(?:\.\d+)?)[ ,]+(-?\d+(?:\.\d+)?)")


def parse_svg(svg_path):
    """返回 dict: canvas, nodes{id:{x,y,w,h,label,fs}}, edges[{eid,kind,pts,stroke,dash}],
    legend[{kind,stroke,dash,label}], bboxes[(desc,x0,y0,x1,y1)]。"""
    tree = ET.parse(svg_path)
    root = tree.getroot()
    canvas = {"x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0}
    vb = (root.get("viewBox") or "").replace(",", " ").split()
    if len(vb) == 4:
        canvas = {"x": _f(vb[0]), "y": _f(vb[1]), "w": _f(vb[2]), "h": _f(vb[3])}

    info = {"canvas": canvas, "nodes": {}, "edges": [], "legend": [], "bboxes": []}
    legend_entries = []

    def rec(el, in_defs, g_node, g_eid, g_kind, g_leg):
        t = _local(el.tag)
        a = el.attrib
        if t == "defs":
            in_defs = True
        if t == "g":
            if a.get("data-legend-entry") is not None:
                g_leg = {"kind": a.get("data-kind", ""), "stroke": None,
                         "dash": None, "label": ""}
                legend_entries.append(g_leg)
            if a.get("data-node-id") is not None:
                g_node = a.get("data-node-id")
            if a.get("data-eid") is not None:
                g_eid = a.get("data-eid")
                g_kind = a.get("data-kind")
        if not in_defs:
            if t == "rect" and g_node is not None:
                nd = info["nodes"].setdefault(g_node, {"label": "", "fs": 10.0})
                nd.update({"x": _f(a.get("x")), "y": _f(a.get("y")),
                           "w": _f(a.get("width")), "h": _f(a.get("height"))})
                info["bboxes"].append((f"node:{g_node}", nd["x"], nd["y"],
                                       nd["x"] + nd["w"], nd["y"] + nd["h"]))
            elif t == "path" and g_eid is not None:
                pts = [(_f(m.group(1)), _f(m.group(2)))
                       for m in PATH_NUM.finditer(a.get("d", ""))]
                info["edges"].append({"eid": g_eid, "kind": g_kind, "pts": pts,
                                      "stroke": (a.get("stroke") or "").lower(),
                                      "dash": _norm_dash(a.get("stroke-dasharray"))})
                if pts:
                    xs = [p[0] for p in pts]
                    ys = [p[1] for p in pts]
                    info["bboxes"].append((f"edge:{g_eid}", min(xs), min(ys),
                                           max(xs), max(ys)))
            elif t == "line" and g_leg is not None and g_leg["stroke"] is None:
                g_leg["stroke"] = (a.get("stroke") or "").lower()
                g_leg["dash"] = _norm_dash(a.get("stroke-dasharray"))
                x1, y1 = _f(a.get("x1")), _f(a.get("y1"))
                x2, y2 = _f(a.get("x2")), _f(a.get("y2"))
                info["bboxes"].append((f"legend:{g_leg['kind']}", min(x1, x2),
                                       min(y1, y2), max(x1, x2), max(y1, y2)))
            elif t == "text":
                x, y = _f(a.get("x")), _f(a.get("y"))
                content = "".join(el.itertext())
                if g_node is not None and a.get("data-badge") is None:
                    nd = info["nodes"].setdefault(g_node, {"x": 0, "y": 0,
                                                           "w": 0, "h": 0, "label": ""})
                    nd["label"] = nd.get("label", "") + content
                    nd["fs"] = _f(a.get("font-size"), 10.0)
                if g_leg is not None and a.get("data-badge") is None:
                    g_leg["label"] += content
                fs = _f(a.get("font-size"), 10.0)
                info["bboxes"].append((f"text:{(content or '?')[:12]}", x, y - fs,
                                       x + est_w(content, fs), y + fs * 0.3))
        for c in el:
            rec(c, in_defs, g_node, g_eid, g_kind, g_leg)

    rec(root, False, None, None, None, None)
    info["legend"] = legend_entries
    return info


# ---------- 字体探测 ----------

def cjk_font_available():
    exe = shutil.which("fc-list")
    if exe:
        try:
            r = subprocess.run([exe, ":lang=zh", "family"],
                               capture_output=True, timeout=30)
            if r.stdout.strip():
                return True
        except Exception:
            pass
    fixed = ["/System/Library/Fonts/PingFang.ttc",
             "/System/Library/Fonts/STHeiti Light.ttc",
             "/System/Library/Fonts/STHeiti Medium.ttc",
             "/Library/Fonts/Arial Unicode.ttf"]
    if any(os.path.exists(p) for p in fixed):
        return True
    pats = ["/usr/share/fonts/**/*NotoSansCJK*", "/usr/share/fonts/**/*NotoSerifCJK*",
            "/usr/share/fonts/**/*wqy*", "/usr/share/fonts/**/*WenQuanYi*",
            "/usr/share/fonts/**/*SourceHan*"]
    return any(glob.glob(p, recursive=True) for p in pats)


# ---------- 检测器 ----------

def run_checks(ir, svg, corpus, corpus_ws, corpus_loose, export_pdf, export_png):
    defects = []

    def add(code, sev, element, evidence):
        defects.append({"code": code, "severity": sev, "element": element,
                        "evidence": evidence, "suggested_fix": FIX[code]})

    ir_nodes = {str(n.get("id")): n for n in ir.get("nodes", [])}
    ir_edges = ir.get("edges", [])

    # --- DANGLING_EDGE（IR 级）---
    for i, e in enumerate(ir_edges):
        eid = str(e.get("id") or f"e{i + 1}")
        for end in ("from", "to"):
            nid = str(e.get(end))
            if nid not in ir_nodes:
                add("DANGLING_EDGE", "error", eid,
                    f"边 {eid} 的 {end} 端点 '{nid}' 不在 IR nodes 中"
                    f"（现有: {sorted(ir_nodes)[:8]}…）")

    # --- DANGLING_EDGE（几何级）---
    boxes = [(nd["x"], nd["y"], nd["w"], nd["h"])
             for nd in svg["nodes"].values() if nd.get("w")]

    def touches(x, y):
        for bx, by, bw, bh in boxes:
            if bx - TOUCH_TOL <= x <= bx + bw + TOUCH_TOL and \
               by - TOUCH_TOL <= y <= by + bh + TOUCH_TOL:
                return True
        return False

    for e in svg["edges"]:
        if len(e["pts"]) < 2:
            add("DANGLING_EDGE", "error", e["eid"], f"边 {e['eid']} 路径点数不足")
            continue
        x0, y0 = e["pts"][0]
        x1, y1 = e["pts"][-1]
        if not touches(x0, y0):
            add("DANGLING_EDGE", "error", e["eid"],
                f"边 {e['eid']} 起点 ({x0:.1f},{y0:.1f}) 未触及任何节点盒")
        if not touches(x1, y1):
            add("DANGLING_EDGE", "error", e["eid"],
                f"边 {e['eid']} 终点 ({x1:.1f},{y1:.1f}) 未触及任何节点盒（箭头悬空）")

    # --- REVERSED_FLOW ---
    svg_edge_by_eid = {e["eid"]: e for e in svg["edges"]}
    for i, e in enumerate(ir_edges):
        eid = str(e.get("id") or f"e{i + 1}")
        na, nb = ir_nodes.get(str(e.get("from"))), ir_nodes.get(str(e.get("to")))
        if not (na and nb):
            continue
        oa, ob = na.get("order"), nb.get("order")
        seq_like = e.get("kind") == "sequence" or (
            isinstance(oa, (int, float)) and isinstance(ob, (int, float)))
        if seq_like and isinstance(oa, (int, float)) and isinstance(ob, (int, float)):
            if oa >= ob:
                add("REVERSED_FLOW", "error", eid,
                    f"顺序语义边 {eid}: from({na.get('label')}, order={oa}) "
                    f">= to({nb.get('label')}, order={ob})，流向与步骤顺序矛盾")
            elif eid in svg_edge_by_eid:
                pts = svg_edge_by_eid[eid]["pts"]
                if len(pts) >= 2 and pts[-1][0] < pts[0][0] - 1.0:
                    add("REVERSED_FLOW", "warn", eid,
                        f"边 {eid} order 递增但箭头向左（终点 x={pts[-1][0]:.1f} < "
                        f"起点 x={pts[0][0]:.1f}），与声明顺序不符")

    # --- NUMBERING_GAP ---
    ordered = sorted(((int(n["order"]), str(n["id"]), str(n.get("label", "")))
                      for n in ir.get("nodes", [])
                      if isinstance(n.get("order"), (int, float))
                      and not isinstance(n.get("order"), bool)))
    if ordered:
        nums = [o[0] for o in ordered]
        expect = list(range(1, len(nums) + 1))
        if nums != expect:
            missing = sorted(set(expect) - set(nums))
            dup = sorted({x for x in nums if nums.count(x) > 1})
            add("NUMBERING_GAP", "error", ",".join(o[1] for o in ordered),
                f"有序节点编号 {nums} 不是连续 1..{len(nums)}"
                f"（缺 {missing or '无'}；重复 {dup or '无'}）")
        if corpus:
            step_nums = [int(m) for m in
                         re.findall(r"步骤\s*([0-9]{1,2})", corpus)]
            if not step_nums:
                step_nums = [int(m) for m in
                             re.findall(r"(?:^|\n)\s*([0-9]{1,2})[.、)]", corpus)]
            if step_nums:
                n_src = max(step_nums)
                if n_src != len(nums):
                    add("NUMBERING_GAP", "warn", "ir.nodes",
                        f"源文本枚举了 {n_src} 个步骤，但 IR 只有 {len(nums)} "
                        f"个有序节点（编号与正文错位风险）")
            else:
                add("NUMBERING_GAP", "warn", "ir.nodes",
                    "源文本中未找到可枚举的步骤序号，无法核对步数（人工确认）")

    # --- LABEL_SOURCE_MISMATCH ---
    if corpus:
        for n in ir.get("nodes", []):
            label = str(n.get("label", ""))
            if not label:
                continue
            if norm_ws(label) in corpus_ws:
                continue
            toks = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{1,}|[一-鿿]+", label)
            missing = []
            for t in toks:
                if re.fullmatch(r"[A-Za-z0-9_\-]+", t):
                    if norm_ws(t) not in corpus_ws:
                        missing.append(t)
                else:
                    if norm_ws(t) in corpus_ws:
                        continue
                    grams = [t[i:i + 2] for i in range(len(t) - 1)] or [t]
                    hit = sum(1 for g in grams if norm_ws(g) in corpus_ws)
                    if hit / len(grams) < 0.7:
                        missing.append(t)
            if missing:
                add("LABEL_SOURCE_MISMATCH", "warn", str(n.get("id")),
                    f"节点 '{label}' 的词元在源文本中找不到: {missing}")

    # --- LEGEND_MISMATCH ---
    used = {}
    for e in svg["edges"]:
        used.setdefault(e["kind"], set()).add((e["stroke"], e["dash"]))
    leg_by_kind = {}
    for ent in svg["legend"]:
        leg_by_kind.setdefault(ent["kind"], ent)
    for kind in sorted(used):
        styles = used[kind]
        ent = leg_by_kind.get(kind)
        if ent is None:
            add("LEGEND_MISMATCH", "error", f"legend:{kind}",
                f"边类型 {kind} 实际使用样式 {sorted(styles)}，但图例中没有对应条目")
        else:
            ls = (ent["stroke"], ent["dash"])
            if ls not in styles:
                add("LEGEND_MISMATCH", "error", f"legend:{kind}",
                    f"图例色块 (stroke={ent['stroke']}, dash={ent['dash']}) "
                    f"与边实际样式 {sorted(styles)} 不一致")
    for kind in sorted(leg_by_kind):
        if kind not in used:
            add("LEGEND_MISMATCH", "warn", f"legend:{kind}",
                f"图例条目 {kind} 在图中没有被任何边使用")

    # --- TEXT_OVERFLOW ---
    for nid, nd in svg["nodes"].items():
        label, w, fs = nd.get("label", ""), nd.get("w", 0), nd.get("fs", 10.0)
        if not label or not w:
            continue
        est = est_w(label, fs)
        if est > w + 0.01:
            add("TEXT_OVERFLOW", "error", nid,
                f"标签 '{label[:20]}…' 估算宽 {est:.1f} > 盒宽 {w:.1f}")
        elif est > 0.9 * w:
            add("TEXT_OVERFLOW", "warn", nid,
                f"标签 '{label[:20]}…' 估算宽 {est:.1f} 达盒宽 {w:.1f} 的 "
                f"{est / w * 100:.0f}%（>90%）")

    # --- FONT_RISK ---
    labels = "".join(str(n.get("label", "")) for n in ir.get("nodes", []))
    labels += "".join(str(e.get("label", "")) for e in ir_edges)
    labels += str(ir.get("title", ""))
    if has_cjk(labels) and not cjk_font_available():
        add("FONT_RISK", "warn", "canvas",
            "标签含 CJK 字符但未探测到中文字体（fc-list 无 zh / 常见路径无 "
            "PingFang、NotoSansCJK、文泉驿）；导出后中文可能变方框")

    # --- CANVAS_OVERFLOW ---
    cv = svg["canvas"]
    if cv["w"] and cv["h"]:
        for desc, x0, y0, x1, y1 in svg["bboxes"]:
            if x0 < cv["x"] - CANVAS_TOL or y0 < cv["y"] - CANVAS_TOL or \
               x1 > cv["x"] + cv["w"] + CANVAS_TOL or \
               y1 > cv["y"] + cv["h"] + CANVAS_TOL:
                add("CANVAS_OVERFLOW", "error", desc,
                    f"元素 {desc} 包围盒 ({x0:.1f},{y0:.1f})-({x1:.1f},{y1:.1f}) "
                    f"超出画布 viewBox 0 0 {cv['w']:.1f} {cv['h']:.1f}")

    # --- EXPORT_FAIL ---
    for fmt, path in (("pdf", export_pdf), ("png", export_png)):
        if not path:
            continue
        if not os.path.exists(path):
            add("EXPORT_FAIL", "error", fmt, f"导出文件不存在: {path}")
            continue
        size = os.path.getsize(path)
        if size == 0:
            add("EXPORT_FAIL", "error", fmt, f"导出文件为零字节: {path}")
            continue
        try:
            with open(path, "rb") as f:
                head = f.read(8)
        except OSError as exc:
            add("EXPORT_FAIL", "error", fmt, f"导出文件不可读: {exc}")
            continue
        magic = b"%PDF" if fmt == "pdf" else b"\x89PNG\r\n\x1a\n"
        if not head.startswith(magic):
            add("EXPORT_FAIL", "error", fmt,
                f"导出文件头 {head[:8]!r} 不是有效 {fmt.upper()} 魔数: {path}")

    # --- UNVERIFIED_QUOTE ---
    if corpus:
        items = [(f"node:{n.get('id')}", n.get("source")) for n in ir.get("nodes", [])]
        items += [(f"edge:{e.get('id') or 'e' + str(i + 1)}", e.get("source"))
                  for i, e in enumerate(ir_edges)]
        for elem, src in items:
            q = (src or {}).get("quote") if isinstance(src, dict) else None
            if q and norm_loose(str(q)) not in corpus_loose:
                add("UNVERIFIED_QUOTE", "warn", elem,
                    f"{elem} 的 source.quote 在源文本中找不到: '{str(q)[:40]}…'")

    return defects


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("ir")
    ap.add_argument("svg")
    ap.add_argument("source_dir")
    ap.add_argument("--report", default="qc_report.json")
    ap.add_argument("--round", type=int, default=None)
    ap.add_argument("--export-pdf", default=None)
    ap.add_argument("--export-png", default=None)
    args = ap.parse_args(argv[1:])

    report = {"ir": os.path.abspath(args.ir), "svg": os.path.abspath(args.svg),
              "source_dir": os.path.abspath(args.source_dir),
              "round": args.round, "defects": [], "notes": [],
              "summary": {"errors": 0, "warns": 0, "total": 0, "codes": []}}
    try:
        with open(args.ir, "r", encoding="utf-8") as f:
            ir = json.load(f)
        svg = parse_svg(args.svg)
        corpus, notes = load_corpus(args.source_dir)
        report["notes"] = notes
        defects = run_checks(ir, svg, corpus, norm_ws(corpus), norm_loose(corpus),
                             args.export_pdf, args.export_png)
        report["defects"] = defects
        errs = sum(1 for d in defects if d["severity"] == "error")
        warns = len(defects) - errs
        report["summary"] = {
            "errors": errs, "warns": warns, "total": len(defects),
            "codes": sorted({d["code"] for d in defects})}
    except Exception as exc:  # 质检器自身也不许抛
        report["notes"].append(f"QC 内部异常: {type(exc).__name__}: {exc}")
        report["summary"] = {"errors": -1, "warns": 0, "total": 0,
                             "codes": ["QC_INTERNAL_ERROR"]}
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    s = report["summary"]
    print(f"[qc_figure] errors={s['errors']} warns={s['warns']} "
          f"codes={s['codes']} -> {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
