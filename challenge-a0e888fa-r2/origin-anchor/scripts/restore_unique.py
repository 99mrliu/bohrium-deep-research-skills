#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""restore_unique.py — 有限恢复：只对“唯一可解”的单元格用恒等式反解恢复。

恢复充要条件（对 primary 可疑单元格 c）：
  1. c 参与的每条 VIOLATED 等式中，c 都是其中唯一的 primary 可疑单元格；
  2. 由这些等式反解出的候选值互相一致（点候选两两在容差内；点候选落在区间候选内）；
  3. 反解值满足字典物理界；
  4. 至少存在一条可反解的等式。
任一条件不满足 → 保留原值，仅在 digest 中记录未恢复原因。绝不插补、绝不发明数值。

输入：原始 CSV（UTF-8 规范化副本）、structure.json、equations.jsonl、suspect_map.csv、constraints.json
输出（写入 --out-dir）：
  cleaned.csv             恢复后的表（未恢复单元格原样保留）
  restoration_ledger.csv  仅含被恢复单元格的台账
  digest.md               摘要（全部数字由产物重算；含恢复后等式复评）

退出码：0 完成；2 参数 / IO 错误。
"""
import argparse
import csv
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import consistency_check as cc  # noqa: E402


def sha256_of(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def fmt_like(v, decimals):
    if decimals == 0:
        return str(int(round(v)))
    return f"{v:.{decimals}f}"


# ---------------------------------------------------------------- 反解
def solve(eq, cell_key, cells, hw):
    """从等式 eq 反解 cell_key 的候选值。

    返回 (kind, payload)：
      ("point", (value, tol))     点候选及其等式容差
      ("interval", (lo, hi, tol)) 区间候选（由其他单元格的舍入半宽推出）
      ("unsupported", reason)     该等式类型不支持反解此位置
    """
    t = eq["type"]
    v = {k: cells[k].get("value") for k in eq["cells"]}
    if any(x is None for x in v.values()):
        return ("unsupported", "等式含缺值单元格")
    if t in ("col_sum", "subtotal_sum"):
        if cell_key == eq["target"]:
            return ("point", (sum(v[k] for k in eq["summands"]), eq.get("tolerance") or 0.0))
        if cell_key in eq["summands"]:
            others = sum(v[k] for k in eq["summands"] if k != cell_key)
            return ("point", (v[eq["target"]] - others, eq.get("tolerance") or 0.0))
        return ("unsupported", "单元格不在等式中")
    if t == "percent":
        num, den, pct = v[eq["numerator"]], v[eq["denominator"]], v[eq["target"]]
        tol = eq.get("tolerance") or 0.0
        if cell_key == eq["target"]:
            if den == 0:
                return ("unsupported", "分母为 0")
            return ("point", (100.0 * num / den, tol))
        h = hw(eq["target"])  # 报告百分比的舍入半宽
        if cell_key == eq["numerator"]:
            lo = (pct - h) * den / 100.0
            hi = (pct + h) * den / 100.0
            return ("interval", (min(lo, hi), max(lo, hi), tol))
        if cell_key == eq["denominator"]:
            if pct - h <= 0:
                return ("unsupported", "百分比区间跨 0，无法反解分母")
            lo = num * 100.0 / (pct + h)
            hi = num * 100.0 / (pct - h)
            return ("interval", (min(lo, hi), max(lo, hi), tol))
        return ("unsupported", "单元格不在等式中")
    if t == "mean_of_sum":
        sm, nn, mn = v[eq["sum_cell"]], v[eq["n_cell"]], v[eq["target"]]
        tol = eq.get("tolerance") or 0.0
        h = hw(eq["target"])
        if cell_key == eq["target"]:
            if nn == 0:
                return ("unsupported", "n 为 0")
            return ("point", (sm / nn, tol))
        if cell_key == eq["sum_cell"]:
            return ("interval", ((mn - h) * nn, (mn + h) * nn, tol))
        if cell_key == eq["n_cell"]:
            if mn - h <= 0:
                return ("unsupported", "均值区间跨 0，无法反解 n")
            lo = sm / (mn + h)
            hi = sm / (mn - h)
            return ("interval", (min(lo, hi), max(lo, hi), tol))
        return ("unsupported", "单元格不在等式中")
    if t == "weighted_mean":
        tol = eq.get("tolerance") or 0.0
        if cell_key == eq["target"]:
            M = sum(v[m] * v[n] for m, n in eq["pairs"])
            N = sum(v[n] for _, n in eq["pairs"])
            if N == 0:
                return ("unsupported", "Σn 为 0")
            return ("point", (M / N, tol))
        for m, n in eq["pairs"]:
            if cell_key == m:
                if v[n] == 0:
                    return ("unsupported", "权重 n 为 0")
                N = sum(v[n2] for _, n2 in eq["pairs"])
                rest = sum(v[m2] * v[n2] for m2, n2 in eq["pairs"] if m2 != m)
                tgt = v[eq["target"]]
                h = hw(eq["target"])
                lo = ((tgt - h) * N - rest) / v[n]
                hi = ((tgt + h) * N - rest) / v[n]
                return ("interval", (min(lo, hi), max(lo, hi), tol))
        return ("unsupported", "不支持从加权均值等式反解该位置")
    if t == "unit_pair":
        tol = eq.get("tolerance") or 0.0
        if cell_key == eq["cell_b"]:
            return ("point", (v[eq["cell_a"]] * eq["factor"], tol))
        if cell_key == eq["cell_a"]:
            if eq["factor"] == 0:
                return ("unsupported", "factor 为 0")
            return ("point", (v[eq["cell_b"]] / eq["factor"], tol))
        return ("unsupported", "单元格不在等式中")
    return ("unsupported", f"未知等式类型 {t}")


TYPE_PRIORITY = {"col_sum": 0, "subtotal_sum": 1, "unit_pair": 2,
                 "mean_of_sum": 3, "percent": 4, "weighted_mean": 5}


def main(argv=None):
    ap = argparse.ArgumentParser(description="唯一可解单元格的有限恢复")
    ap.add_argument("csv_path", help="UTF-8 规范化后的原始 CSV")
    ap.add_argument("structure", help="structure.json")
    ap.add_argument("equations", help="equations.jsonl")
    ap.add_argument("suspect_map", help="suspect_map.csv")
    ap.add_argument("constraints", help="constraints.json")
    ap.add_argument("--out-dir", default=".", help="输出目录")
    args = ap.parse_args(argv)

    try:
        structure = cc.load_json(args.structure)
        cfg = cc.load_json(args.constraints)
        eqs = [json.loads(line) for line in open(args.equations, "r", encoding="utf-8") if line.strip()]
    except (OSError, json.JSONDecodeError) as e:
        print(f"[restore_unique] 输入读取失败: {e}", file=sys.stderr)
        return 2

    cells = structure["cells"]
    header = structure["header"]
    row_labels = structure["row_labels"]

    # suspect_map → primary 集合
    primary = set()
    try:
        with open(args.suspect_map, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                if row["class"] == "primary":
                    primary.add(f"R{row['row_index']}C{row['column_index']}")
    except (OSError, KeyError) as e:
        print(f"[restore_unique] suspect_map.csv 读取失败: {e}", file=sys.stderr)
        return 2

    evaluate = cc.make_evaluator(structure, cfg)
    for eq in eqs:  # 复评，确保状态与本次输入一致
        status, expected, observed, tol, note = evaluate(eq)
        eq["status"], eq["expected"], eq["observed"], eq["tolerance"] = status, expected, observed, tol
        if note:
            eq["note"] = note

    roles = cfg.get("roles", {})
    exact_cols = set()
    for it in roles.get("n_columns", []):
        exact_cols.add(it["index"])
    for it in roles.get("count_columns", []):
        exact_cols.add(it["index"])
    for it in roles.get("additive_columns", []):
        exact_cols.add(it["index"])
    for it in roles.get("sum_mean_pairs", []):
        exact_cols.add(it["sum"])

    def hw(key):
        c = cells.get(key, {})
        if c.get("value") is None:
            return 0.0
        if c.get("decimals") == 0 and c.get("col") in exact_cols:
            return 0.0
        return 0.5 * (10.0 ** -(c.get("decimals") or 0))

    violated = [e for e in eqs if e["status"] == "VIOLATED"]
    cell_vio = {}
    for e in violated:
        for k in e["cells"]:
            cell_vio.setdefault(k, []).append(e)

    bounds_by_col = {}
    for item in cfg.get("bounds", []):
        bounds_by_col.setdefault(item["column"], []).append(item)

    # ---------------------------------------------------------------- 逐 primary 裁决
    ledger = []          # 恢复成功的台账行
    unresolved = []      # (cell, reason)
    for k in sorted(primary, key=lambda x: (cells[x]["row"], cells[x]["col"])):
        vio = cell_vio.get(k, [])
        if not vio:
            unresolved.append((k, "未参与任何违反等式"))
            continue
        # 条件 1：每条违反等式中 k 是唯一 primary
        blocker = [e["id"] for e in vio if sum(1 for c in e["cells"] if c in primary) != 1]
        if blocker:
            unresolved.append((k, f"等式 {', '.join(blocker)} 含多个主要可疑单元格，非唯一可解"))
            continue
        # 反解候选
        points, intervals, unsup = [], [], []
        for e in vio:
            kind, payload = solve(e, k, cells, hw)
            if kind == "point":
                points.append((e["id"], e["type"], payload[0], payload[1]))
            elif kind == "interval":
                intervals.append((e["id"], e["type"], payload[0], payload[1], payload[2]))
            else:
                unsup.append((e["id"], payload))
        if not points and not intervals:
            unresolved.append((k, "所有违反等式均不支持反解: "
                                  + "; ".join(f"{i}({r})" for i, r in unsup)))
            continue
        # 条件 2：候选一致性
        conflict = None
        for i in range(len(points)):
            for j in range(i + 1, len(points)):
                id1, _, p1, t1 = points[i]
                id2, _, p2, t2 = points[j]
                if abs(p1 - p2) > t1 + t2 + 1e-9:
                    conflict = f"点候选冲突: {id1}→{cc.fmt(p1)} vs {id2}→{cc.fmt(p2)}"
                    break
            if conflict:
                break
        if not conflict:
            for pid, _, p, tp in points:
                for iid, _, lo, hi, ti in intervals:
                    if p < lo - tp - ti - 1e-9 or p > hi + tp + ti + 1e-9:
                        conflict = f"点候选 {pid}→{cc.fmt(p)} 落在区间候选 {iid}=[{cc.fmt(lo)}, {cc.fmt(hi)}] 之外"
                        break
                if conflict:
                    break
        if not conflict and not points and intervals:
            lo = max(x[2] for x in intervals)
            hi = min(x[3] for x in intervals)
            if lo > hi + 1e-9:
                conflict = "区间候选交集为空"
        if conflict:
            unresolved.append((k, conflict))
            continue
        # 选定恢复值：优先求和类点候选，其次其他点候选，再次区间交集中点
        value = None
        basis = ""
        if points:
            points.sort(key=lambda x: (TYPE_PRIORITY.get(x[1], 9), x[0]))
            value = points[0][2]
            basis = f"点候选 {points[0][0]}（{points[0][1]}）"
        else:
            lo = max(x[2] for x in intervals)
            hi = min(x[3] for x in intervals)
            value = (lo + hi) / 2.0
            basis = f"区间候选交集 [{cc.fmt(lo)}, {cc.fmt(hi)}] 中点"
        # 整数贴靠：原单元格 decimals==0 时取最近整数并回验
        dec = cells[k].get("decimals") or 0
        if dec == 0:
            snapped = float(round(value))
            ok = True
            for _, _, lo, hi, _ in intervals:
                if snapped < lo - 1e-9 or snapped > hi + 1e-9:
                    ok = False
                    break
            if ok:
                value = snapped
            basis += "；整数列贴靠"
        # 条件 3：字典界
        ci = cells[k]["col"]
        slack = 0.5 * (10.0 ** -dec)
        bnd_fail = None
        for b in bounds_by_col.get(ci, []):
            if b.get("min") is not None and value < b["min"] - slack:
                bnd_fail = f"恢复值 {cc.fmt(value)} 低于字典下界 {cc.fmt(b['min'])}（{b.get('source','')}）"
            if b.get("max") is not None and value > b["max"] + slack:
                bnd_fail = f"恢复值 {cc.fmt(value)} 高于字典上界 {cc.fmt(b['max'])}（{b.get('source','')}）"
        if bnd_fail:
            unresolved.append((k, bnd_fail))
            continue
        eq_ids = ";".join(e["id"] for e in vio)
        ledger.append({
            "cell": k,
            "row_index": cells[k]["row"],
            "row_label": row_labels[cells[k]["row"]],
            "column_index": ci,
            "column_header": header[ci],
            "old_value": cells[k]["raw"],
            "new_value": fmt_like(value, dec),
            "equation_ids": eq_ids,
            "method": basis,
        })

    # ---------------------------------------------------------------- 写 cleaned.csv
    try:
        raw_text = open(args.csv_path, "r", encoding="utf-8").read()
    except OSError as e:
        print(f"[restore_unique] 无法读取 {args.csv_path}: {e}", file=sys.stderr)
        return 2
    rows = [r for r in csv.reader(raw_text.splitlines())]
    nonempty = [r for r in rows if any((c or "").strip() for c in r)]
    header_row = nonempty[0]
    data_rows = nonempty[1:]
    replace = {(e["row_index"], e["column_index"]): e["new_value"] for e in ledger}
    out_lines = [",".join(header_row)]
    for ri, row in enumerate(data_rows):
        row = row + [""] * (len(header_row) - len(row)) if len(row) < len(header_row) else row
        new_row = [replace.get((ri, ci), cell) for ci, cell in enumerate(row)]
        out_lines.append(",".join(new_row))
    cleaned_path = f"{args.out_dir}/cleaned.csv"
    with open(cleaned_path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(out_lines) + "\n")

    # ---------------------------------------------------------------- 台账
    ledger_path = f"{args.out_dir}/restoration_ledger.csv"
    with open(ledger_path, "w", encoding="utf-8", newline="") as f:
        f.write("row_index,row_label,column_index,column_header,old_value,new_value,equation_ids,method\n")
        for e in ledger:
            f.write(",".join([
                str(e["row_index"]), e["row_label"].replace(",", "，"),
                str(e["column_index"]), e["column_header"].replace(",", "，"),
                e["old_value"], e["new_value"], e["equation_ids"], e["method"].replace(",", "，"),
            ]) + "\n")

    # ---------------------------------------------------------------- 恢复后复评
    for e in ledger:
        cells[e["cell"]]["value"] = float(e["new_value"])
        cells[e["cell"]]["raw"] = e["new_value"]
    post_violated, post_passed, post_undef = [], 0, 0
    for eq in eqs:
        status, expected, observed, tol, note = evaluate(eq)
        if status == "VIOLATED":
            post_violated.append(eq)
        elif status == "PASS":
            post_passed += 1
        else:
            post_undef += 1

    # suspect_map 统计（从产物重算）
    cls_count = {}
    conf_count = {}
    with open(args.suspect_map, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            cls_count[row["class"]] = cls_count.get(row["class"], 0) + 1
            conf_count[row["confidence"]] = conf_count.get(row["confidence"], 0) + 1

    D = []
    D.append("# 恢复摘要（digest，数字由产物重算）")
    D.append("")
    D.append(f"- suspect_map.csv 单元格分类: "
             + ", ".join(f"{k}={v}" for k, v in sorted(cls_count.items())))
    D.append(f"- 置信分布: " + ", ".join(f"{k}={v}" for k, v in sorted(conf_count.items())))
    D.append(f"- 恢复单元格数（restoration_ledger.csv 行数）: {len(ledger)}")
    D.append(f"- 未恢复主要可疑单元格数: {len(unresolved)}")
    D.append(f"- 恢复后等式复评: 通过 {post_passed}，仍违反 {len(post_violated)}，无法评估 {post_undef}")
    D.append(f"- cleaned.csv sha256: `{sha256_of(cleaned_path)}`")
    D.append(f"- restoration_ledger.csv sha256: `{sha256_of(ledger_path)}`")
    D.append("")
    if ledger:
        D.append("## 已恢复")
        D.append("")
        D.append("| 单元格 | 行 | 列 | 旧值 | 新值 | 依据等式 | 方法 |")
        D.append("|---|---|---|---|---|---|---|")
        for e in ledger:
            D.append(f"| {e['cell']} | R{e['row_index']} `{e['row_label']}` | "
                     f"C{e['column_index']} `{e['column_header']}` | {e['old_value']} | {e['new_value']} "
                     f"| {e['equation_ids']} | {e['method']} |")
        D.append("")
    if unresolved:
        D.append("## 未恢复（保留原值，写入不确定性）")
        D.append("")
        D.append("| 单元格 | 行 | 列 | 当前值 | 原因 |")
        D.append("|---|---|---|---|---|")
        for k, reason in unresolved:
            c = cells[k]
            D.append(f"| {k} | R{c['row']} `{row_labels[c['row']]}` | C{c['col']} `{header[c['col']]}` "
                     f"| {c['raw']} | {reason} |")
        D.append("")
    if post_violated:
        D.append("## 恢复后仍违反的等式")
        D.append("")
        for eq in post_violated:
            D.append(f"- {eq['id']}（{eq['type']}）`{eq['expression']}`：观测 {cc.fmt(eq['observed'])}，"
                     f"期望 {cc.fmt(eq['expected'])}")
        D.append("")
    with open(f"{args.out_dir}/digest.md", "w", encoding="utf-8") as f:
        f.write("\n".join(D))

    print(f"[restore_unique] 恢复 {len(ledger)} 格；未恢复 {len(unresolved)} 格；"
          f"恢复后仍违反等式 {len(post_violated)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
