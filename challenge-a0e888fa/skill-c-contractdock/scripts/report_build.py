#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_build.py — 从产物重算质量报告（标准库，确定性）。

质量报告的每一个数字都由本脚本从**产物本身**重算，杜绝"报告数字与结果表
对不上"：输入 cleaned.csv（清洗表）、ledger.csv（逐格台账，列约定为
row,field,action,old,new,rule,source）、可选 raw.csv（原始表），输出：
  quality_report.json   机器可读（含输入文件 sha256 与重算时间外的全部细节）
  quality_report.md     人读版
  report_preview.svg    字段级问题计数条形图（纯 SVG，无依赖，可直接预览）

退出码：0 正常；2 参数错误。
"""
import argparse
import csv
import hashlib
import json
import os
import sys


def sha256_file(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def read_table(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    return rows[0], rows[1:]


def build(cleaned_path, ledger_path, raw_path):
    header, data = read_table(cleaned_path)
    rep = {"artifacts": {}, "table": {"rows_out": len(data), "cols": len(header)},
           "fields": {}, "actions": {}, "ledger_entries": 0}
    rep["artifacts"]["cleaned"] = {"path": os.path.abspath(cleaned_path),
                                   "sha256": sha256_file(cleaned_path)}
    # 字段级空值率（按清洗表实算）
    for j, name in enumerate(header):
        empty = sum(1 for r in data if j >= len(r) or not r[j].strip())
        rep["fields"][name] = {"empty_cells": empty,
                               "empty_rate": round(empty / max(1, len(data)), 6)}
    if raw_path:
        try:
            _, rdata = read_table(raw_path)
            rep["table"]["rows_in"] = len(rdata)
            rep["table"]["rows_dropped"] = len(rdata) - len(data)
            rep["artifacts"]["raw"] = {"path": os.path.abspath(raw_path),
                                       "sha256": sha256_file(raw_path)}
        except OSError:
            rep["table"]["rows_in"] = None
    if ledger_path and os.path.isfile(ledger_path):
        with open(ledger_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        if rows:
            lheader, lrows = rows[0], rows[1:]
            fi = lheader.index("field") if "field" in lheader else 1
            ai = lheader.index("action") if "action" in lheader else 2
            rep["ledger_entries"] = len(lrows)
            per_field = {}
            for r in lrows:
                act = r[ai] if ai < len(r) else "?"
                fld = r[fi] if fi < len(r) else "?"
                rep["actions"][act] = rep["actions"].get(act, 0) + 1
                per_field.setdefault(fld, {})
                per_field[fld][act] = per_field[fld].get(act, 0) + 1
            for fld, acts in per_field.items():
                rep["fields"].setdefault(fld, {})["ledger_actions"] = acts
        rep["artifacts"]["ledger"] = {"path": os.path.abspath(ledger_path),
                                      "sha256": sha256_file(ledger_path)}
    return rep


def render_svg(rep, path):
    fields = [(k, v.get("empty_cells", 0),
               sum((v.get("ledger_actions") or {}).values()))
              for k, v in rep["fields"].items()]
    if not fields:
        fields = [("(无字段)", 0, 0)]
    w = 640
    bar_h, gap, top = 18, 8, 40
    h = top + len(fields) * (bar_h + gap) + 20
    maxv = max(1, max(max(e, l) for _, e, l in fields))
    x0, scale_w = 160, 420
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
             'font-family="monospace" font-size="12">' % (w, h),
             '<rect width="100%" height="100%" fill="#ffffff"/>',
             '<text x="10" y="22" font-size="14" font-weight="bold">'
             '字段级问题计数（重算自产物 · 合成示例则数据为合成）</text>',
             '<text x="%d" y="34" fill="#666">空值格数(蓝) / 台账处置数(橙)</text>'
             % x0]
    for i, (name, empty, acts) in enumerate(fields):
        y = top + i * (bar_h + gap)
        w1 = int(scale_w * empty / maxv)
        w2 = int(scale_w * acts / maxv)
        label = name if len(name) <= 18 else name[:17] + "…"
        parts.append('<text x="%d" y="%d" text-anchor="end">%s</text>'
                     % (x0 - 8, y + 13, label.replace("&", "&amp;")
                        .replace("<", "&lt;")))
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#4c78a8"/>'
                     % (x0, y, w1, bar_h))
        parts.append('<rect x="%d" y="%d" width="%d" height="%d" fill="#f58518"/>'
                     % (x0 + w1, y, w2, bar_h))
        parts.append('<text x="%d" y="%d" fill="#333">%d/%d</text>'
                     % (x0 + w1 + w2 + 6, y + 13, empty, acts))
    parts.append('</svg>')
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def render_md(rep):
    t = rep["table"]
    md = ["# 数据质量报告（由产物重算生成）", "",
          "- 清洗表行数: %s；列数: %s" % (t["rows_out"], t["cols"])]
    if t.get("rows_in") is not None:
        md.append("- 原始行数: %s；丢弃行数: %s" % (t["rows_in"], t["rows_dropped"]))
    md.append("- 台账条目: %d" % rep["ledger_entries"])
    if rep["actions"]:
        md.append("- 处置动作统计: %s" % json.dumps(rep["actions"],
                                                    ensure_ascii=False))
    md += ["", "## 字段级", ""]
    for name, f in rep["fields"].items():
        line = "- `%s`: 空值 %d (%.1f%%)" % (name, f.get("empty_cells", 0),
                                             100 * f.get("empty_rate", 0))
        if f.get("ledger_actions"):
            line += "；台账 %s" % json.dumps(f["ledger_actions"],
                                             ensure_ascii=False)
        md.append(line)
    md += ["", "## 产物指纹", ""]
    for k, a in rep["artifacts"].items():
        md.append("- %s: `%s` sha256=%s" % (k, a["path"], a["sha256"][:16] + "…"))
    return "\n".join(md) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cleaned", required=True, help="清洗表 CSV")
    ap.add_argument("--ledger", default=None, help="逐格台账 CSV")
    ap.add_argument("--raw", default=None, help="原始表 CSV（可选，算丢弃行数）")
    ap.add_argument("--out", required=True, help="产物目录")
    args = ap.parse_args()
    if not os.path.isfile(args.cleaned):
        print("ERROR: cleaned 不存在", file=sys.stderr)
        sys.exit(2)
    os.makedirs(args.out, exist_ok=True)
    rep = build(args.cleaned, args.ledger, args.raw)
    with open(os.path.join(args.out, "quality_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "quality_report.md"), "w",
              encoding="utf-8") as f:
        f.write(render_md(rep))
    render_svg(rep, os.path.join(args.out, "report_preview.svg"))
    print(json.dumps({"status": "ok", "fields": len(rep["fields"]),
                      "ledger_entries": rep["ledger_entries"],
                      "out": os.path.abspath(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
