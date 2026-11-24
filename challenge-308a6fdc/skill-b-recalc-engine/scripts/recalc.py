#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recalc.py — 数据摄入 + 派生量重算引擎（仅 Python3 标准库，确定性，秒级）

功能：
  1. 扫描输入目录中的 CSV/TSV 表格（sniff 分隔符与表头，跳过 # 注释行）；
  2. 每列判定 标识列 / 分组列 / 数值列，生成 dataset_profile.json；
  3. 对每张表、按「分组列 × 数值列」组合确定性重算
     n / mean / median / SD(样本) / SEM / min / max；
     并以每组列中"首个出现的组"为基线（对照组），重算
     差值 B-A、比值 B/A、百分比变化 (B-A)/A×100%；
  4. 每条派生量都记录 formula 与 inputs（表、列、组、行数），可溯源。

输出（写入 --output-dir）：
  dataset_profile.json   数据集画像
  derived_values.json    机器可读的全部重算派生量
  recalc_table.md        人可读的 Markdown 重算表

退出码：0 成功；2 硬失败（目录不存在、参数错误等）。无 CSV/TSV 时仍为 0，
但输出空画像并打印降级提示，由上游如实降级为"仅原文数字核对"。
"""

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

# 视为缺失值的字面量
MISSING = {"", "NA", "N/A", "NaN", "nan", "null", "None", "-"}
# 常见标识列名（不参与统计与分组）
IDENTIFIER_NAMES = {"id", "idx", "index", "no", "num", "number",
                    "replicate", "rep", "sample", "编号", "序号", "样本"}
# 支持的表格扩展名
TABLE_SUFFIXES = {".csv", ".tsv"}


def fmt(x):
    """统一数值显示：6 位有效数字；None 显示为 NA。"""
    if x is None:
        return "NA"
    if isinstance(x, float):
        return f"{x:.6g}"
    return str(x)


def read_table(path):
    """读取一张 CSV/TSV：跳过 # 注释行，sniff 分隔符与表头。
    返回 (headers, rows)，rows 为 dict 列表。失败返回 (None, 错误说明)。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return None, f"读取失败: {e}"
    lines = [l for l in text.splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    if not lines:
        return None, "空表或全部为注释行"
    sample = "\n".join(lines[:50])
    # sniff 分隔符；失败则按扩展名兜底
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        delim = dialect.delimiter
    except csv.Error:
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
    # sniff 表头；失败则默认首行为表头
    try:
        has_header = csv.Sniffer().has_header(sample)
    except csv.Error:
        has_header = True
    reader = csv.reader(lines, delimiter=delim)
    rows_raw = list(reader)
    if not rows_raw:
        return None, "无可解析行"
    if has_header:
        headers = [h.strip() or f"col{i}" for i, h in enumerate(rows_raw[0])]
        body = rows_raw[1:]
    else:
        headers = [f"col{i}" for i in range(len(rows_raw[0]))]
        body = rows_raw
    rows = []
    for r in body:
        if len(r) < len(headers):
            r = r + [""] * (len(headers) - len(r))
        rows.append({h: (r[i].strip() if i < len(r) else "")
                     for i, h in enumerate(headers)})
    if not rows:
        return None, "只有表头没有数据行"
    return (headers, rows), None


def classify_columns(headers, rows):
    """列类型判定：
    numeric    —— 全部非缺失值可解析为 float；
    identifier —— numeric 且列名像标识列（id/replicate/编号等）；
    group      —— 其余（非数值列，用作分组）。
    返回 {列名: {"type": ..., "missing": 缺失计数, "n": 有效计数}}。"""
    profile = {}
    for h in headers:
        vals = [row[h] for row in rows]
        present = [v for v in vals if v not in MISSING]
        missing = len(vals) - len(present)
        numeric = bool(present)
        if numeric:
            for v in present:
                try:
                    float(v)
                except ValueError:
                    numeric = False
                    break
        if numeric and h.strip().lower() in IDENTIFIER_NAMES:
            ctype = "identifier"
        elif numeric:
            ctype = "numeric"
        else:
            ctype = "group"
        profile[h] = {"type": ctype, "missing": missing, "n": len(present)}
    return profile


def basic_stats(xs):
    """对一组浮点数确定性重算描述性统计。SD 为样本标准差（n-1）。"""
    n = len(xs)
    if n == 0:
        return None
    mean = statistics.fmean(xs)
    sd = statistics.stdev(xs) if n >= 2 else None
    sem = sd / (n ** 0.5) if sd is not None else None
    return {
        "n": n,
        "mean": mean,
        "median": statistics.median(xs),
        "sd": sd,
        "sem": sem,
        "min": min(xs),
        "max": max(xs),
    }


def recalc_table(name, headers, rows, colprof, values):
    """对一张表执行全量重算，派生量追加到 values 列表（就地）。"""
    group_cols = [h for h in headers if colprof[h]["type"] == "group"]
    num_cols = [h for h in headers if colprof[h]["type"] == "numeric"]
    sections = []  # 人可读 markdown 片段

    def add(kind, formula, inputs, value, column, group_col=None,
            group=None, extra=None):
        rec = {
            "id": f"D{len(values) + 1:04d}",
            "table": name,
            "kind": kind,
            "column": column,
            "group_column": group_col,
            "group": group,
            "value": value,
            "formula": formula,
            "inputs": inputs,
        }
        if extra:
            rec.update(extra)
        values.append(rec)
        return rec

    # —— 情形 1：无分组列 —— 整列描述性统计
    if not group_cols:
        for col in num_cols:
            xs = [float(r[col]) for r in rows if r[col] not in MISSING]
            st = basic_stats(xs)
            if not st:
                continue
            for k in ("n", "mean", "median", "sd", "sem", "min", "max"):
                add(k, FORMULAS[k],
                    {"column": col, "rows": st["n"]},
                    st[k], col)
            sections.append((col, None, {"整列": st}))
        return sections

    # —— 情形 2：每个 分组列 × 数值列
    for gcol in group_cols:
        # 组的出现顺序（首个出现的组 = 基线/对照组）
        order = []
        bucket = {}
        for r in rows:
            g = r[gcol]
            if g in MISSING:
                continue
            if g not in bucket:
                bucket[g] = []
                order.append(g)
        for col in num_cols:
            stats_by_group = {}
            for g in order:
                xs = [float(r[col]) for r in rows
                      if r[gcol] == g and r[col] not in MISSING]
                st = basic_stats(xs)
                if st:
                    stats_by_group[g] = st
                    for k in ("n", "mean", "median", "sd", "sem", "min", "max"):
                        add(k, FORMULAS[k],
                            {"column": col, "group_column": gcol,
                             "group": g, "rows": st["n"]},
                            st[k], col, gcol, g)
            sections.append((col, gcol, stats_by_group))

            # —— 两分组派生量：以首个出现的组为基线 A，其余各组为 B ——
            if len(stats_by_group) >= 2:
                base = order[0]
                A = stats_by_group[base]["mean"]
                for g in order[1:]:
                    if g not in stats_by_group:
                        continue
                    B = stats_by_group[g]["mean"]
                    inp = {"column": col, "group_column": gcol,
                           "baseline_group": base,
                           "baseline_n": stats_by_group[base]["n"],
                           "target_group": g,
                           "target_n": stats_by_group[g]["n"]}
                    add("diff", "diff = mean(B) - mean(A)", inp, B - A,
                        col, gcol, None,
                        {"from_group": base, "to_group": g})
                    if A != 0:
                        add("ratio", "ratio = mean(B) / mean(A)", inp, B / A,
                            col, gcol, None,
                            {"from_group": base, "to_group": g})
                        add("pct_change",
                            "pct_change = (mean(B) - mean(A)) / mean(A) * 100%",
                            inp, (B - A) / A * 100.0, col, gcol, None,
                            {"from_group": base, "to_group": g})
    return sections


FORMULAS = {
    "n": "n = count(x)",
    "mean": "mean = sum(x) / n",
    "median": "median = 排序后中位值",
    "sd": "SD = sqrt( sum((x - mean)^2) / (n - 1) )  # 样本标准差",
    "sem": "SEM = SD / sqrt(n)",
    "min": "min(x)",
    "max": "max(x)",
}


def render_markdown(profiles, all_sections, values):
    """生成人可读重算表 recalc_table.md。"""
    out = ["# 重算表（recalc_table）",
           "",
           "由 scripts/recalc.py 从原始表格确定性重算生成；"
           "所有派生量附公式与输入溯源，禁止手工改动。",
           ""]
    for name, headers, rows, colprof, sections in all_sections:
        out.append(f"## 表 `{name}`（{len(rows)} 行 × {len(headers)} 列）")
        out.append("")
        out.append("列类型：" + "；".join(
            f"`{h}`={colprof[h]['type']}(缺失{colprof[h]['missing']})"
            for h in headers))
        out.append("")
        if not sections:
            out.append("（无数值列，未产生重算统计）")
            out.append("")
        for col, gcol, stats_by_group in sections:
            title = (f"### 数值列 `{col}`" +
                     (f" × 分组列 `{gcol}`" if gcol else "（整列，无分组）"))
            out.append(title)
            out.append("")
            out.append("| 组 | n | mean | median | SD | SEM | min | max |")
            out.append("|---|---|---|---|---|---|---|---|")
            for g, st in stats_by_group.items():
                out.append("| {g} | {n} | {mean} | {median} | {sd} | {sem}"
                           " | {min} | {max} |".format(
                               g=g, n=st["n"], mean=fmt(st["mean"]),
                               median=fmt(st["median"]), sd=fmt(st["sd"]),
                               sem=fmt(st["sem"]), min=fmt(st["min"]),
                               max=fmt(st["max"])))
            out.append("")
            if gcol and len(stats_by_group) >= 2:
                base = next(iter(stats_by_group))
                out.append(f"两分组派生量（基线 A = `{base}`，"
                           "按组在数据中的首次出现顺序确定）：")
                out.append("")
                out.append("| 对比 | 差值 B-A | 比值 B/A | 百分比变化 (B-A)/A×100% |")
                out.append("|---|---|---|---|")
                for v in values:
                    if (v["table"] == name and v["kind"] == "pct_change"
                            and v["column"] == col
                            and v["inputs"].get("group_column") == gcol):
                        # 直接从派生量列表中取同对比的 diff / ratio，保证溯源一致
                        diff = next((d["value"] for d in values
                                     if d["table"] == name
                                     and d["kind"] == "diff"
                                     and d["column"] == col
                                     and d["from_group"] == v["from_group"]
                                     and d["to_group"] == v["to_group"]), None)
                        ratio = next((d["value"] for d in values
                                      if d["table"] == name
                                      and d["kind"] == "ratio"
                                      and d["column"] == col
                                      and d["from_group"] == v["from_group"]
                                      and d["to_group"] == v["to_group"]), None)
                        out.append(f"| {v['to_group']} vs {v['from_group']} "
                                   f"| {fmt(diff)} | {fmt(ratio)} "
                                   f"| {fmt(v['value'])}% |")
                out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="摄入 CSV/TSV 并确定性重算全部派生量（仅标准库）")
    ap.add_argument("--input-dir", default="/input", help="输入材料目录")
    ap.add_argument("--output-dir", default="/app/output", help="输出目录")
    args = ap.parse_args(argv)

    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    if not in_dir.is_dir():
        print(f"[硬失败] 输入目录不存在: {in_dir}", file=sys.stderr)
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    # —— 1. 数据摄入 ——
    tables = sorted(p for p in in_dir.rglob("*")
                    if p.is_file() and p.suffix.lower() in TABLE_SUFFIXES)
    profile = {"tool": "recalc.py", "input_dir": str(in_dir),
               "tables": [], "degraded": False}
    values = []          # 全部派生量（机器可读）
    all_sections = []    # 供 markdown 渲染
    for p in tables:
        parsed, err = read_table(p)
        if err:
            profile["tables"].append({"file": p.name, "error": err})
            print(f"[警告] 跳过 {p.name}: {err}", file=sys.stderr)
            continue
        headers, rows = parsed
        colprof = classify_columns(headers, rows)
        profile["tables"].append({
            "file": p.name, "rows": len(rows), "columns": len(headers),
            "column_profile": colprof,
        })
        sections = recalc_table(p.name, headers, rows, colprof, values)
        all_sections.append((p.name, headers, rows, colprof, sections))
        print(f"[摄入] {p.name}: {len(rows)} 行, 列类型 "
              + ", ".join(f"{h}={colprof[h]['type']}" for h in headers))

    if not values:
        profile["degraded"] = True
        print("[降级] 未找到可重算的 CSV/TSV 数值数据，"
              "后续核验只能做'仅原文数字核对'。", file=sys.stderr)

    # —— 2. 写输出 ——
    (out_dir / "dataset_profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    derived = {"tool": "recalc.py", "input_dir": str(in_dir),
               "derived_count": len(values), "values": values}
    (out_dir / "derived_values.json").write_text(
        json.dumps(derived, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "recalc_table.md").write_text(
        render_markdown(profile, all_sections, values), encoding="utf-8")

    print(f"[完成] 重算派生量 {len(values)} 条 → "
          f"{out_dir}/derived_values.json, recalc_table.md, "
          f"dataset_profile.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
