#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""table_scan.py — 发表汇总表的结构挖掘（纯标准库，确定性输出）。

读取已规范化为 UTF-8 的 CSV，检测：
  * 合计 / 小计行（标签模式：合计/总计/Total/Overall/小计/Subtotal ...）
  * 百分比列（表头含 %/percent/百分比/构成比 等，或单元格带 % 后缀）
  * n 列（表头为 n/N/样本量/例数/人数 等）
  * 数值网格（每个单元格的原文、数值、小数位、是否带 % 后缀）

输出（写入 --out-dir）：
  structure.json   机器可读结构（供 consistency_check.py 消费）
  scan_report.md   人类可读报告

退出码：
  0  正常完成
  2  参数 / IO 错误
  3  空表或无表头
"""
import argparse
import csv
import hashlib
import json
import re
import sys

TOTAL_PAT = re.compile(
    r"(合计|总计|共计|总和|总例数|全部|总体|total|overall|all[\s_\-]?(subjects|patients|participants|cases)?)",
    re.IGNORECASE,
)
SUBTOTAL_PAT = re.compile(
    r"(小计|亚组合计|分组合计|subtotal|sub[\s_\-]?total)",
    re.IGNORECASE,
)
PCT_HEADER_PAT = re.compile(
    r"(%|percent|pct|百分比|百分率|百分数|构成比|占比|发生率|应答率|阳性率|率$)",
    re.IGNORECASE,
)
N_HEADER_PAT = re.compile(
    r"^(n|N|样本量|例数|人数|受试者数|样本数|count|sample[_\s]?size|n[_\s]?total)$"
)
NUM_PAT = re.compile(r"^-?\d+(\.\d+)?$")

NUMERIC_RATIO = 0.8  # 一列中可解析为数值的非空单元格占比达到该值即视为数值列


def parse_cell(text):
    """返回 (value, decimals, percent_suffix)。非数值返回 (None, None, False)。"""
    t = (text or "").strip()
    if not t:
        return None, None, False
    is_pct = t.endswith("%")
    if is_pct:
        t = t[:-1].strip()
    t = t.replace(",", "")
    if NUM_PAT.match(t):
        decimals = len(t.split(".", 1)[1]) if "." in t else 0
        return float(t), decimals, is_pct
    return None, None, False


def main(argv=None):
    ap = argparse.ArgumentParser(description="发表汇总表结构挖掘")
    ap.add_argument("csv_path", help="已规范化为 UTF-8 的 CSV 文件")
    ap.add_argument("--out-dir", default=".", help="输出目录（默认当前目录）")
    args = ap.parse_args(argv)

    try:
        raw = open(args.csv_path, "rb").read()
    except OSError as e:
        print(f"[table_scan] 无法读取 {args.csv_path}: {e}", file=sys.stderr)
        return 2
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        print(f"[table_scan] 输入不是 UTF-8（请先做编码规范化）: {e}", file=sys.stderr)
        return 2

    rows = [r for r in csv.reader(text.splitlines())]
    rows = [r for r in rows if any((c or "").strip() for c in r)]
    if len(rows) < 2:
        print("[table_scan] 空表或无数据行（只有 0/1 行），退出码 3", file=sys.stderr)
        return 3
    header = [(h or "").strip() for h in rows[0]]
    if not any(header):
        print("[table_scan] 表头为空，退出码 3", file=sys.stderr)
        return 3
    data = rows[1:]
    n_cols = len(header)
    # 对齐列数（短行补空串）
    data = [r + [""] * (n_cols - len(r)) if len(r) < n_cols else r[:n_cols] for r in data]

    # 解析网格
    cells = {}
    numeric_count = [0] * n_cols
    nonempty_count = [0] * n_cols
    pct_suffix_seen = [False] * n_cols
    for ri, row in enumerate(data):
        for ci in range(n_cols):
            raw_cell = row[ci]
            val, dec, is_pct = parse_cell(raw_cell)
            key = f"R{ri}C{ci}"
            cells[key] = {
                "row": ri,
                "col": ci,
                "raw": raw_cell.strip(),
                "value": val,
                "decimals": dec,
                "percent_suffix": is_pct,
            }
            if raw_cell.strip():
                nonempty_count[ci] += 1
            if val is not None:
                numeric_count[ci] += 1
                if is_pct:
                    pct_suffix_seen[ci] = True

    numeric_columns = [
        ci
        for ci in range(n_cols)
        if numeric_count[ci] > 0
        and numeric_count[ci] >= NUMERIC_RATIO * max(1, nonempty_count[ci])
    ]
    numeric_set = set(numeric_columns)

    # 标签列：数值占比最低的最左列
    def num_ratio(ci):
        return numeric_count[ci] / max(1, nonempty_count[ci])

    label_column = min(range(n_cols), key=lambda ci: (num_ratio(ci), ci))

    # 合计 / 小计行
    total_rows, subtotal_rows = [], []
    row_labels = []
    for ri, row in enumerate(data):
        label = row[label_column].strip()
        row_labels.append(label)
        if SUBTOTAL_PAT.search(label):
            subtotal_rows.append({"index": ri, "label": label})
        elif TOTAL_PAT.search(label):
            total_rows.append({"index": ri, "label": label})
    flagged = {r["index"] for r in total_rows} | {r["index"] for r in subtotal_rows}
    leaf_rows = [ri for ri in range(len(data)) if ri not in flagged]

    # 小计行的成员：其上方、上一个小计/合计行之后的连续叶行块
    blocks = []
    current = []
    for ri in range(len(data)):
        if ri in {r["index"] for r in subtotal_rows}:
            blocks.append({"subtotal_index": ri, "members": list(current)})
            current = []
        elif ri in {r["index"] for r in total_rows}:
            pass
        else:
            current.append(ri)

    percent_columns = [
        ci
        for ci in numeric_columns
        if PCT_HEADER_PAT.search(header[ci]) or pct_suffix_seen[ci]
    ]
    n_columns = [ci for ci in numeric_columns if N_HEADER_PAT.match(header[ci])]

    structure = {
        "source_file": args.csv_path,
        "sha256": sha256,
        "n_rows": len(data),
        "n_cols": n_cols,
        "header": header,
        "label_column": label_column,
        "row_labels": row_labels,
        "numeric_columns": numeric_columns,
        "percent_columns": percent_columns,
        "n_columns": n_columns,
        "total_rows": total_rows,
        "subtotal_rows": subtotal_rows,
        "subtotal_blocks": blocks,
        "leaf_rows": leaf_rows,
        "cells": cells,
    }
    out_structure = f"{args.out_dir}/structure.json"
    with open(out_structure, "w", encoding="utf-8") as f:
        json.dump(structure, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    # 人类可读报告
    lines = []
    lines.append("# 结构挖掘报告（table_scan）")
    lines.append("")
    lines.append(f"- 源文件: `{args.csv_path}`")
    lines.append(f"- sha256: `{sha256}`")
    lines.append(f"- 规模: {len(data)} 个数据行 × {n_cols} 列")
    lines.append(f"- 标签列: C{label_column} `{header[label_column]}`")
    lines.append(
        "- 数值列: " + (", ".join(f"C{c} `{header[c]}`" for c in numeric_columns) or "（无）")
    )
    lines.append(
        "- 百分比列: " + (", ".join(f"C{c} `{header[c]}`" for c in percent_columns) or "（未检出）")
    )
    lines.append("- n 列: " + (", ".join(f"C{c} `{header[c]}`" for c in n_columns) or "（未检出）"))
    lines.append(
        "- 合计行: "
        + (", ".join(f"R{r['index']} `{r['label']}`" for r in total_rows) or "（未检出）")
    )
    lines.append(
        "- 小计行: "
        + (", ".join(f"R{r['index']} `{r['label']}`" for r in subtotal_rows) or "（未检出）")
    )
    for b in blocks:
        lab = row_labels[b["subtotal_index"]]
        mem = ", ".join(f"R{m} `{row_labels[m]}`" for m in b["members"]) or "（空块）"
        lines.append(f"  - R{b['subtotal_index']} `{lab}` 的成员: {mem}")
    lines.append("- 叶行: " + (", ".join(f"R{r} `{row_labels[r]}`" for r in leaf_rows) or "（无）"))
    lines.append("")
    lines.append("## 下一步")
    lines.append("")
    if not total_rows and not subtotal_rows:
        lines.append("- ⚠ 未检出合计/小计行：列合计恒等式将不可用，consistency_check 将降级为仅行内等式与字典界检查。")
    if not percent_columns:
        lines.append("- ⚠ 未检出百分比列：百分比闭合恒等式不可用（可在 constraints.json 的 roles.percent_columns 中显式指定）。")
    lines.append("- 请据数据字典填写 constraints.json（schema 见 references/aggregate_structures.md），然后运行 consistency_check.py。")
    lines.append("")
    with open(f"{args.out_dir}/scan_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[table_scan] 完成: {len(data)} 行 × {n_cols} 列; "
          f"合计行 {len(total_rows)}, 小计行 {len(subtotal_rows)}, "
          f"百分比列 {len(percent_columns)}, n 列 {len(n_columns)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
