#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""field_survey.py — 字段勘测器：扫描数据表（可选对照数据字典），生成裁定模板。

产物（写入 --out 目录）：
  survey_report.md         紧凑人读摘要（字段画像、哨兵计数、键候选、单位串）
  decisions.template.json  裁定模板：Agent 对照数据字典/QC 规则/工单逐项填写
                           policy 与依据（source），交给 adjudicate.py 执行。

本脚本只勘测、不处置；任何值的修改都由 adjudicate.py 按显式裁定执行并留痕。
退出码：0 正常；2 参数/文件错误；3 表为空或无法解析。
"""
import argparse
import csv
import json
import os
import re
import sys

SENTINELS = ["-999", "-9999", "-99", "NA", "N/A", "null", "NULL", "None",
             "nan", "NaN", "ND", "n.d.", "—", "–", "空白", "缺失", ""]
RE_SCI = re.compile(r"^[+-]?\d+(\.\d+)?[eE][+-]?\d+$")
RE_NUM = re.compile(r"^[+-]?\d+(\.\d+)?$")
RE_UNIT_SUFFIX = re.compile(r"^[+-]?\d+(\.\d+)?\s*([a-zA-Zμµ%/][a-zA-Zμµ%/0-9.·^-]*)$")
RE_LT = re.compile(r"^<\s*(\d.*)$")
FULLWIDTH = {chr(ord("０") + i): str(i) for i in range(10)}
FULLWIDTH.update({"．": ".", "　": " "})


def norm_text(s):
    t = s.strip()
    t = "".join(FULLWIDTH.get(c, c) for c in t)
    t = re.sub(r"\s+", " ", t)
    return t.casefold()


def survey(rows, header):
    n = len(header)
    fields = {}
    for j, name in enumerate(header):
        vals = [r[j] if j < len(r) else "" for r in rows]
        f = {"column_index": j, "non_empty": 0, "sentinels": {}, "numeric": 0,
             "sci_notation": 0, "lt_lod": 0, "unit_strings": {}, "samples": []}
        for v in vals:
            t = v.strip()
            if t in SENTINELS:
                f["sentinels"][t if t else "<空>"] = f["sentinels"].get(t if t else "<空>", 0) + 1
                continue
            f["non_empty"] += 1
            if RE_NUM.match(t):
                f["numeric"] += 1
            elif RE_SCI.match(t):
                f["sci_notation"] += 1
            elif RE_LT.match(t):
                f["lt_lod"] += 1
            m = RE_UNIT_SUFFIX.match(t)
            if m:
                f["unit_strings"][m.group(2)] = f["unit_strings"].get(m.group(2), 0) + 1
            if len(f["samples"]) < 3 and t not in [s for s in f["samples"]]:
                f["samples"].append(t)
        fields[name] = f
    # 键候选：归一化后的唯一性
    keys = {}
    for j, name in enumerate(header):
        norms = [norm_text(r[j]) if j < len(r) else "" for r in rows]
        uniq = len(set(norms))
        keys[name] = {"rows": len(rows), "distinct": uniq,
                      "unique": uniq == len(rows) and len(rows) > 0,
                      "dup_groups": len(rows) - uniq}
    return fields, keys


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", help="数据表（CSV，首行为表头）")
    ap.add_argument("--dict", dest="dictfile", default=None, help="数据字典（可选，仅摘引）")
    ap.add_argument("--out", required=True, help="产物目录")
    args = ap.parse_args()

    if not os.path.isfile(args.table):
        print("ERROR: 文件不存在: %s" % args.table, file=sys.stderr)
        sys.exit(2)
    with open(args.table, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 1 or not rows[0]:
        print("ERROR: 表为空或无表头", file=sys.stderr)
        sys.exit(3)
    header, data = rows[0], rows[1:]
    fields, keys = survey(data, header)

    os.makedirs(args.out, exist_ok=True)
    template = {
        "table": os.path.abspath(args.table),
        "key_columns": ["<填：工单/字典指定的真实主键列名>"],
        "dedup": {"normalize": ["casefold", "strip", "fullwidth", "collapse_space"],
                  "keep": "most_complete",
                  "on_conflict": "review_queue"},
        "fields": {},
        "global_rules": {
            "no_imputation": True,
            "unknown_unit": "keep_and_flag",
            "note": "引擎绝不插补；仅执行本文件显式声明的处置"
        }
    }
    for name, f in fields.items():
        template["fields"][name] = {
            "role": "measurement|identifier|metadata 三选一",
            "unit": {"observed": sorted(f["unit_strings"].keys()),
                     "canonical": "<填：规范单位；必须在单位注册表内>"},
            "missing": {tok: "<not_detected|below_lod|entry_missing|true_zero>"
                        for tok in f["sentinels"]},
            "policy": "mark|empty|keep 三选一（缺失值的处置）",
            "bounds": {"min": None, "max": None},
            "source": "<填：依据定位，如 dictionary.md#L12 / workorder 第3条>"
        }
    with open(os.path.join(args.out, "decisions.template.json"), "w",
              encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)

    md = ["# 字段勘测报告", "",
          "- 表: `%s` | 数据行: %d | 列: %d" % (args.table, len(data), len(header)), "",
          "## 字段画像", ""]
    for name, f in fields.items():
        md.append("### `%s`" % name)
        md.append("- 非空 %d；数值 %d；科学计数法 %d；<LOD 形 %d" %
                  (f["non_empty"], f["numeric"], f["sci_notation"], f["lt_lod"]))
        if f["sentinels"]:
            md.append("- 哨兵: %s" % json.dumps(f["sentinels"], ensure_ascii=False))
        if f["unit_strings"]:
            md.append("- 内嵌单位串: %s" % json.dumps(f["unit_strings"], ensure_ascii=False))
        md.append("- 样例: %s" % " | ".join(f["samples"]))
    md += ["", "## 主键候选（归一化后唯一性）", ""]
    for name, k in keys.items():
        md.append("- `%s`: distinct=%d/%d%s%s" % (
            name, k["distinct"], k["rows"],
            " ✅唯一" if k["unique"] else "",
            " ⚠重复组 %d" % k["dup_groups"] if k["dup_groups"] else ""))
    md += ["", "下一步：复制 decisions.template.json 为 decisions.json，对照数据字典、",
           "单位/QC 规则与工单逐项填写 policy、missing 分类、bounds 与 source，",
           "然后运行 adjudicate.py。"]
    if args.dictfile:
        md += ["", "数据字典摘引（%s 前 40 行）：" % args.dictfile, ""]
        try:
            with open(args.dictfile, encoding="utf-8", errors="replace") as f:
                md += ["  " + l.rstrip() for l in f.readlines()[:40]]
        except OSError:
            md.append("  <字典文件不可读>")
    with open(os.path.join(args.out, "survey_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    print(json.dumps({"status": "ok", "rows": len(data), "cols": len(header),
                      "out": os.path.abspath(args.out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
