#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""figure_audit.py — 图表证据机器审计（exit 0 = 全过，exit 1 = 任一违例）。

用法：
  python3 figure_audit.py --output-dir /app/output --result /app/output/result.json

检查：
  (a) report.md / figures.md 引用的每个图文件存在、签名有效
      （PNG magic bytes + IHDR 尺寸；SVG 根元素 + viewBox + 图元数量）、尺寸非平凡；
  (b) figures.md 图注中每组 n / 均值 / SD 与 result.json 对应值一致
      （n 精确；均值、SD 容差 0.005，即 2 位小数四舍五入容差）；p 记法一致；
  (c) 选择规则合规：k 组/两组比较必须有 boxplot/violin/ECDF 之一覆盖；
      任一组 n<30 的均值条形图（bar_se/bar_sd/mean_bar/dynamite）→ 违例；
  (d) result.json 中每个做过假设检验的分析至少有一张合规图，或显式 waiver。

违例码：MISSING_FIGURE / BAD_SIGNATURE / CAPTION_NUMBER_MISMATCH /
        RULE_VIOLATION_BAR / MISSING_COVERAGE
"""
from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys

COVERAGE_TYPES = {"boxplot_jitter", "boxplot", "boxplot_points", "violin", "ecdf"}
BAR_TYPES = {"bar_se", "bar_sd", "mean_bar", "dynamite", "bar_mean"}
MEAN_TOL = 0.005 + 1e-9     # 2 位小数四舍五入容差
MIN_FILE_BYTES = 400
FIG_REF_RE = re.compile(r"fig[\w.-]*\.(?:png|svg)")
FIELD_RE = re.compile(r"^-\s*([a-z_]+):\s*(.*)$")
TRIPLE_RE = re.compile(r"组\s*([^：|]+)：n=(\d+)，均值=(-?\d+(?:\.\d+)?)，SD=(-?\d+(?:\.\d+)?)")
P_RE = re.compile(r"p(<0\.0001|=\d+(?:\.\d+)?)")


class Violations:
    def __init__(self):
        self.items = []

    def add(self, code, msg):
        self.items.append((code, msg))
        print("VIOLATION %s: %s" % (code, msg))


def check_png(path, v):
    raw = open(path, "rb").read()
    if len(raw) < MIN_FILE_BYTES:
        v.add("BAD_SIGNATURE", "%s 文件过小（%d 字节）" % (path, len(raw)))
        return
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        v.add("BAD_SIGNATURE", "%s 缺少 PNG magic bytes" % path)
        return
    if raw[12:16] != b"IHDR":
        v.add("BAD_SIGNATURE", "%s 缺少 IHDR 块" % path)
        return
    w, h = struct.unpack(">II", raw[16:24])
    if w < 100 or h < 100:
        v.add("BAD_SIGNATURE", "%s 尺寸非平凡检查失败（%dx%d）" % (path, w, h))


def check_svg(path, v):
    try:
        text = open(path, encoding="utf-8").read()
    except UnicodeDecodeError:
        v.add("BAD_SIGNATURE", "%s 非 UTF-8 文本" % path)
        return
    if len(text.encode("utf-8")) < MIN_FILE_BYTES:
        v.add("BAD_SIGNATURE", "%s 文件过小（%d 字节）" % (path, len(text)))
        return
    head = text[:2048]
    if "<svg" not in head:
        v.add("BAD_SIGNATURE", "%s 前 2KB 无 <svg 根元素" % path)
        return
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(text)
    except ET.ParseError as e:
        v.add("BAD_SIGNATURE", "%s XML 解析失败: %s" % (path, e))
        return
    if not root.tag.endswith("svg"):
        v.add("BAD_SIGNATURE", "%s 根元素不是 svg（%s）" % (path, root.tag))
        return
    vb = root.get("viewBox", "")
    ok_dim = False
    if vb:
        parts = vb.replace(",", " ").split()
        if len(parts) == 4:
            try:
                ok_dim = float(parts[2]) >= 200 and float(parts[3]) >= 150
            except ValueError:
                ok_dim = False
    else:
        try:
            ok_dim = float(root.get("width", "0")) >= 200 and float(root.get("height", "0")) >= 150
        except ValueError:
            ok_dim = False
    if not ok_dim:
        v.add("BAD_SIGNATURE", "%s 尺寸非平凡检查失败（viewBox=%r）" % (path, vb))
    n_elems = sum(1 for e in root.iter()
                  if e.tag.split("}")[-1] in ("rect", "line", "circle", "polyline", "path"))
    if n_elems < 5:
        v.add("BAD_SIGNATURE", "%s 图元数量过少（%d < 5），疑为占位图" % (path, n_elems))


def parse_figures_md(text):
    """按 '## ' 块解析 figures.md，返回 list[dict]。"""
    blocks, cur = [], None
    for line in text.splitlines():
        if line.startswith("## "):
            if cur:
                blocks.append(cur)
            cur = {"heading": line[3:].strip(), "fields": {}}
        elif cur is not None:
            m = FIELD_RE.match(line)
            if m:
                cur["fields"][m.group(1)] = m.group(2).strip()
    if cur:
        blocks.append(cur)
    return blocks


def main(argv=None):
    ap = argparse.ArgumentParser(description="图表证据机器审计")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--result", required=True)
    ap.add_argument("--figures-md", default=None)
    ap.add_argument("--report", default=None)
    args = ap.parse_args(argv)

    v = Violations()
    result = json.load(open(args.result, encoding="utf-8"))
    analyses = result.get("hypothesis_test", {}).get("analyses", [])
    by_id = {a["id"]: a for a in analyses}
    waivers = result.get("figures", {}).get("waivers", {}) or {}

    figmd_path = args.figures_md or os.path.join(args.output_dir, "figures.md")
    report_path = args.report or os.path.join(args.output_dir, "report.md")
    figmd = open(figmd_path, encoding="utf-8").read() if os.path.exists(figmd_path) else ""
    report = open(report_path, encoding="utf-8").read() if os.path.exists(report_path) else ""
    if not figmd:
        v.add("MISSING_COVERAGE", "figures.md 不存在：无任何图表证据")

    blocks = parse_figures_md(figmd)

    # ---------- (a) 引用文件存在 + 签名有效
    refs = set()
    for b in blocks:
        if "file" in b["fields"]:
            refs.add(b["fields"]["file"])
    refs.update(FIG_REF_RE.findall(figmd))
    refs.update(FIG_REF_RE.findall(report))
    n_checked = 0
    for ref in sorted(refs):
        path = os.path.join(args.output_dir, ref)
        if not os.path.exists(path):
            v.add("MISSING_FIGURE", "%s 被引用但不存在" % ref)
            continue
        n_checked += 1
        if ref.lower().endswith(".png"):
            check_png(path, v)
        elif ref.lower().endswith(".svg"):
            check_svg(path, v)
        else:
            v.add("BAD_SIGNATURE", "%s 扩展名不支持" % ref)

    # ---------- (b) 图注数字一致性
    for b in blocks:
        f = b["fields"]
        cap = f.get("caption", "")
        if not cap or "analyses" not in f:
            continue
        triples = {t[0].strip(): (int(t[1]), float(t[2]), float(t[3]))
                   for t in TRIPLE_RE.findall(cap)}
        for aid in [x.strip() for x in f["analyses"].split(",") if x.strip()]:
            a = by_id.get(aid)
            if a is None:
                continue
            for label, g in a["groups"].items():
                lab = re.sub(r"[：:|；;]", "-", str(label))
                if lab not in triples:
                    v.add("CAPTION_NUMBER_MISMATCH",
                          "%s(%s) 图注缺少组 %s 的 n/均值/SD" % (f.get("file", "?"), aid, lab))
                    continue
                n_cap, mean_cap, sd_cap = triples[lab]
                if n_cap != g["n"]:
                    v.add("CAPTION_NUMBER_MISMATCH",
                          "%s(%s) 组 %s：图注 n=%d ≠ result n=%d"
                          % (f.get("file", "?"), aid, lab, n_cap, g["n"]))
                if abs(mean_cap - g["mean"]) > MEAN_TOL:
                    v.add("CAPTION_NUMBER_MISMATCH",
                          "%s(%s) 组 %s：图注均值=%.2f ≠ result %.6f（容差 0.005）"
                          % (f.get("file", "?"), aid, lab, mean_cap, g["mean"]))
                if abs(sd_cap - g["sd"]) > MEAN_TOL:
                    v.add("CAPTION_NUMBER_MISMATCH",
                          "%s(%s) 组 %s：图注 SD=%.2f ≠ result %.6f（容差 0.005）"
                          % (f.get("file", "?"), aid, lab, sd_cap, g["sd"]))
            pm = P_RE.search(cap)
            if pm and "p" in a:
                token = pm.group(1)
                if token.startswith("<"):
                    if not a["p"] < 0.0001:
                        v.add("CAPTION_NUMBER_MISMATCH",
                              "%s(%s) 图注 p<0.0001 与 result p=%.6f 矛盾"
                              % (f.get("file", "?"), aid, a["p"]))
                else:
                    p_cap = float(token[1:])
                    if abs(p_cap - a["p"]) > 0.00005 + 1e-12:
                        v.add("CAPTION_NUMBER_MISMATCH",
                              "%s(%s) 图注 p=%.4f ≠ result p=%.6f"
                              % (f.get("file", "?"), aid, p_cap, a["p"]))

    # ---------- (c) 选择规则合规
    coverage = {}  # aid -> [types]
    for b in blocks:
        f = b["fields"]
        ftype = f.get("type", "")
        for aid in [x.strip() for x in f.get("analyses", "").split(",") if x.strip()]:
            coverage.setdefault(aid, []).append(ftype)
            a = by_id.get(aid)
            if a is None:
                continue
            if ftype in BAR_TYPES and a["design"] in ("two_group", "k_group"):
                small = [lab for lab, g in a["groups"].items() if g["n"] < 30]
                if small:
                    v.add("RULE_VIOLATION_BAR",
                          "%s(%s)：用均值条形图(%s)展示组间比较且组 %s n<30（dynamite plot 陷阱）"
                          % (f.get("file", "?"), aid, ftype,
                             ",".join("%s n=%d" % (l, a["groups"][l]["n"]) for l in small)))

    # ---------- (d) 覆盖：每个检验过的分析有合规图或 waiver
    for a in analyses:
        aid = a["id"]
        if aid in waivers:
            continue
        types = coverage.get(aid, [])
        if a["design"] in ("two_group", "k_group"):
            if not any(t in COVERAGE_TYPES for t in types):
                v.add("MISSING_COVERAGE",
                      "分析 %s（%s by %s，%s）无箱线/小提琴/ECDF 覆盖且无 waiver"
                      % (aid, a["outcome"], a["group_var"], a["method"]))
        else:
            if not types:
                v.add("MISSING_COVERAGE", "分析 %s 无任何图覆盖且无 waiver" % aid)

    print("----")
    print("审计对象: %d 个图文件引用, %d 个 figures.md 块, %d 个分析, %d 个 waiver"
          % (n_checked, len(blocks), len(analyses), len(waivers)))
    if v.items:
        print("AUDIT FAIL: %d 个违例" % len(v.items))
        return 1
    print("AUDIT PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
