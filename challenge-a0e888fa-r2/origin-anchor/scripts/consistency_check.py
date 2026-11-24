#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""consistency_check.py — 恒等式建网、评估、最小命中集故障定位与置信分级。

输入：structure.json（table_scan 产物）+ constraints.json（Agent 据数据字典填写）。
输出（写入 --out-dir）：
  equations.jsonl        全部恒等式（每行一个 JSON，含状态与容差）
  consistency_report.md  逐等式裁决报告
  suspect_map.csv        全数值单元格的置信标注

退出码：
  0  完成（包括存在违规的情形；违规是结果，不是错误）
  2  参数 / IO 错误
  4  constraints.json 校验失败（缺 source、字段不存在、索引越界等）

容差模型（确定性）：
  每个报告值带有舍入半宽 hw = 0.5 * 10^-decimals；
  整数计数字面量（n/计数/可加列中 decimals==0 的单元格）视为精确，hw = 0；
  等式容差 = 各参与单元格半宽经误差传播后的和 + rel * |expected|（rel 默认 1e-6）。
"""
import argparse
import json
import sys
from collections import Counter

ROLE_KEYS_REQUIRE_SOURCE = True


# ---------------------------------------------------------------- 工具
def cell_key(ri, ci):
    return f"R{ri}C{ci}"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fmt(x):
    """确定性数字格式化：整数不带小数点，其余去尾零。"""
    if x is None:
        return ""
    if isinstance(x, int) or (isinstance(x, float) and x.is_integer() and abs(x) < 1e15):
        return str(int(x))
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s


# ---------------------------------------------------------------- 约束校验
def validate_constraints(cfg, structure):
    """返回错误列表；空列表表示通过。"""
    errors = []
    n_cols = structure["n_cols"]
    numeric_set = set(structure["numeric_columns"])

    def check_idx(obj, key, must_numeric=True):
        idx = obj.get(key)
        if not isinstance(idx, int) or isinstance(idx, bool):
            errors.append(f"字段 {key}={idx!r} 不是整数列索引")
            return None
        if idx < 0 or idx >= n_cols:
            errors.append(f"列索引 {key}={idx} 越界（共 {n_cols} 列）")
            return None
        if must_numeric and idx not in numeric_set:
            errors.append(f"列 C{idx} `{structure['header'][idx]}` 不是数值列（{key}）")
            return None
        return idx

    def check_source(obj, where):
        src = obj.get("source")
        if not isinstance(src, str) or not src.strip():
            errors.append(f"{where} 缺少非空 source 定位")

    if not isinstance(cfg, dict):
        return ["constraints.json 顶层必须是 JSON 对象"]
    roles = cfg.get("roles", {})
    if not isinstance(roles, dict):
        return ["constraints.json 的 roles 必须是对象"]

    if "label_column" in roles:
        lc = roles["label_column"]
        check_source(lc, "roles.label_column")
        idx = lc.get("index")
        if not isinstance(idx, int) or idx < 0 or idx >= n_cols:
            errors.append("roles.label_column.index 越界或不是整数")

    for key in ("n_columns", "count_columns", "percent_columns", "mean_columns",
                "additive_columns", "sum_mean_pairs", "bounds", "unit_pairs"):
        if key in roles and not isinstance(roles[key], list):
            errors.append(f"roles.{key} 必须是数组")

    for item in roles.get("n_columns", []):
        check_source(item, "roles.n_columns[]")
        check_idx(item, "index")
    for item in roles.get("count_columns", []):
        check_source(item, "roles.count_columns[]")
        check_idx(item, "index")
    for item in roles.get("additive_columns", []):
        check_source(item, "roles.additive_columns[]")
        check_idx(item, "index")
    for item in roles.get("mean_columns", []):
        check_source(item, "roles.mean_columns[]")
        check_idx(item, "index")
    for item in roles.get("percent_columns", []):
        check_source(item, "roles.percent_columns[]")
        check_idx(item, "index")
        check_idx(item, "numerator")
        check_idx(item, "denominator")
    for item in roles.get("sum_mean_pairs", []):
        check_source(item, "roles.sum_mean_pairs[]")
        check_idx(item, "sum")
        check_idx(item, "mean")
        check_idx(item, "n")
    for item in cfg.get("bounds", []):
        check_source(item, "bounds[]")
        check_idx(item, "column")
        if "min" not in item and "max" not in item:
            errors.append("bounds[] 至少需要 min 或 max 之一")
    for item in cfg.get("unit_pairs", []):
        check_source(item, "unit_pairs[]")
        check_idx(item, "column_a")
        check_idx(item, "column_b")
        if not isinstance(item.get("factor"), (int, float)):
            errors.append("unit_pairs[].factor 必须是数值")
    tol = cfg.get("tolerance", {})
    if tol and not isinstance(tol.get("rel", 0), (int, float)):
        errors.append("tolerance.rel 必须是数值")
    return errors


# ---------------------------------------------------------------- 等式构建
class EquationBuilder:
    def __init__(self, structure, cfg):
        self.s = structure
        self.cfg = cfg
        self.eqs = []
        self.seq = 0

    def add(self, eq):
        self.seq += 1
        eq["id"] = f"E{self.seq:03d}"
        self.eqs.append(eq)
        return eq

    def build(self):
        s = self.s
        roles = self.cfg.get("roles", {})
        leaf = s["leaf_rows"]
        totals = [r["index"] for r in s["total_rows"]]
        blocks = s["subtotal_blocks"]

        n_cols = [it["index"] for it in roles.get("n_columns", [])]
        cnt_cols = [it["index"] for it in roles.get("count_columns", [])]
        add_cols = [it["index"] for it in roles.get("additive_columns", [])]
        pair_sum_cols = [it["sum"] for it in roles.get("sum_mean_pairs", [])]
        src_of = {}
        for it in roles.get("n_columns", []) + roles.get("count_columns", []) \
                + roles.get("additive_columns", []):
            src_of[it["index"]] = it.get("source", "")
        for it in roles.get("sum_mean_pairs", []):
            src_of[it["sum"]] = it.get("source", "")

        additive = sorted(set(n_cols) | set(cnt_cols) | set(add_cols) | set(pair_sum_cols))

        # 1) 列合计 / 小计恒等式
        for c in additive:
            for t in totals:
                summands = [cell_key(r, c) for r in leaf]
                self.add({
                    "type": "col_sum",
                    "target": cell_key(t, c),
                    "summands": summands,
                    "cells": summands + [cell_key(t, c)],
                    "column": c,
                    "expression": " + ".join(summands) + f" = {cell_key(t, c)}",
                    "source": src_of.get(c, ""),
                })
            for b in blocks:
                if not b["members"]:
                    continue
                summands = [cell_key(r, c) for r in b["members"]]
                self.add({
                    "type": "subtotal_sum",
                    "target": cell_key(b["subtotal_index"], c),
                    "summands": summands,
                    "cells": summands + [cell_key(b["subtotal_index"], c)],
                    "column": c,
                    "expression": " + ".join(summands) + f" = {cell_key(b['subtotal_index'], c)}",
                    "source": src_of.get(c, ""),
                })

        # 2) 百分比闭合（逐行）
        all_rows = list(range(s["n_rows"]))
        for item in roles.get("percent_columns", []):
            p, num, den = item["index"], item["numerator"], item["denominator"]
            for r in all_rows:
                self.add({
                    "type": "percent",
                    "target": cell_key(r, p),
                    "numerator": cell_key(r, num),
                    "denominator": cell_key(r, den),
                    "cells": [cell_key(r, num), cell_key(r, den), cell_key(r, p)],
                    "column": p,
                    "expression": f"{cell_key(r, p)} = 100 * {cell_key(r, num)} / {cell_key(r, den)}",
                    "source": item.get("source", ""),
                })

        # 3) mean = sum / n 三角（逐行）
        for item in roles.get("sum_mean_pairs", []):
            sm, mn, nn = item["sum"], item["mean"], item["n"]
            for r in all_rows:
                self.add({
                    "type": "mean_of_sum",
                    "target": cell_key(r, mn),
                    "sum_cell": cell_key(r, sm),
                    "n_cell": cell_key(r, nn),
                    "cells": [cell_key(r, sm), cell_key(r, nn), cell_key(r, mn)],
                    "column": mn,
                    "expression": f"{cell_key(r, mn)} = {cell_key(r, sm)} / {cell_key(r, nn)}",
                    "source": item.get("source", ""),
                })

        # 4) 加权均值（合计行 / 小计行的 mean 列）
        n_for_weight = n_cols[0] if n_cols else None
        for item in roles.get("mean_columns", []):
            mc = item["index"]
            if n_for_weight is None:
                continue
            for t in totals:
                pairs = [[cell_key(r, mc), cell_key(r, n_for_weight)] for r in leaf]
                cells = [cell_key(t, mc)] + [k for pr in pairs for k in pr]
                self.add({
                    "type": "weighted_mean",
                    "target": cell_key(t, mc),
                    "pairs": pairs,
                    "cells": cells,
                    "column": mc,
                    "expression": f"{cell_key(t, mc)} = Σ(mean_i·n_i)/Σn_i（叶行）",
                    "source": item.get("source", ""),
                })
            for b in blocks:
                if not b["members"]:
                    continue
                pairs = [[cell_key(r, mc), cell_key(r, n_for_weight)] for r in b["members"]]
                cells = [cell_key(b["subtotal_index"], mc)] + [k for pr in pairs for k in pr]
                self.add({
                    "type": "weighted_mean",
                    "target": cell_key(b["subtotal_index"], mc),
                    "pairs": pairs,
                    "cells": cells,
                    "expression": f"{cell_key(b['subtotal_index'], mc)} = Σ(mean_i·n_i)/Σn_i（块成员）",
                    "source": item.get("source", ""),
                })

        # 5) 单位对偶列
        for item in self.cfg.get("unit_pairs", []):
            a, bcol, f = item["column_a"], item["column_b"], item["factor"]
            for r in all_rows:
                self.add({
                    "type": "unit_pair",
                    "cell_a": cell_key(r, a),
                    "cell_b": cell_key(r, bcol),
                    "target": cell_key(r, bcol),
                    "factor": f,
                    "cells": [cell_key(r, a), cell_key(r, bcol)],
                    "column": bcol,
                    "expression": f"{cell_key(r, bcol)} = {fmt(f)} * {cell_key(r, a)}",
                    "source": item.get("source", ""),
                })
        return self.eqs


# ---------------------------------------------------------------- 评估
def make_evaluator(structure, cfg):
    cells = structure["cells"]
    roles = cfg.get("roles", {})
    rel = float(cfg.get("tolerance", {}).get("rel", 1e-6))
    exact_cols = set()
    for it in roles.get("n_columns", []):
        exact_cols.add(it["index"])
    for it in roles.get("count_columns", []):
        exact_cols.add(it["index"])
    for it in roles.get("additive_columns", []):
        exact_cols.add(it["index"])
    for it in roles.get("sum_mean_pairs", []):
        exact_cols.add(it["sum"])

    def get(key):
        return cells.get(key, {})

    def hw(key):
        c = get(key)
        if c.get("value") is None:
            return 0.0
        if c.get("decimals") == 0 and c.get("col") in exact_cols:
            return 0.0
        return 0.5 * (10.0 ** -(c.get("decimals") or 0))

    def evaluate(eq):
        """返回 (status, expected, observed, tol, note)。"""
        t = eq["type"]
        vals = {k: get(k).get("value") for k in eq["cells"]}
        if any(v is None for v in vals.values()):
            missing = [k for k, v in vals.items() if v is None]
            return ("UNDEFINED", None, None, None, f"缺值/非数值单元格: {', '.join(missing)}")
        if t in ("col_sum", "subtotal_sum"):
            expected = sum(vals[k] for k in eq["summands"])
            observed = vals[eq["target"]]
            tol = hw(eq["target"]) + sum(hw(k) for k in eq["summands"]) + rel * abs(expected)
        elif t == "percent":
            num, den = vals[eq["numerator"]], vals[eq["denominator"]]
            if den == 0:
                return ("UNDEFINED", None, None, None, "分母为 0")
            expected = 100.0 * num / den
            observed = vals[eq["target"]]
            tol = (hw(eq["target"]) + hw(eq["numerator"]) * 100.0 / abs(den)
                   + hw(eq["denominator"]) * 100.0 * abs(num) / (den * den)
                   + rel * abs(expected))
        elif t == "mean_of_sum":
            sm, nn = vals[eq["sum_cell"]], vals[eq["n_cell"]]
            if nn == 0:
                return ("UNDEFINED", None, None, None, "n 为 0")
            expected = sm / nn
            observed = vals[eq["target"]]
            tol = (hw(eq["target"]) + hw(eq["sum_cell"]) / abs(nn)
                   + hw(eq["n_cell"]) * abs(sm) / (nn * nn) + rel * abs(expected))
        elif t == "weighted_mean":
            M = sum(vals[m] * vals[n] for m, n in eq["pairs"])
            N = sum(vals[n] for _, n in eq["pairs"])
            if N == 0:
                return ("UNDEFINED", None, None, None, "Σn 为 0")
            expected = M / N
            observed = vals[eq["target"]]
            tol = (hw(eq["target"])
                   + sum(abs(vals[n]) * hw(m) + abs(vals[m]) * hw(n) for m, n in eq["pairs"]) / abs(N)
                   + rel * abs(expected))
        elif t == "unit_pair":
            expected = vals[eq["cell_a"]] * eq["factor"]
            observed = vals[eq["cell_b"]]
            tol = hw(eq["cell_b"]) + abs(eq["factor"]) * hw(eq["cell_a"]) + rel * abs(expected)
        else:
            return ("UNDEFINED", None, None, None, f"未知等式类型 {t}")
        diff = abs(observed - expected)
        status = "VIOLATED" if diff > tol + 1e-12 else "PASS"
        return (status, expected, observed, tol, "")

    return evaluate


# ---------------------------------------------------------------- 主流程
def main(argv=None):
    ap = argparse.ArgumentParser(description="汇总表算术自洽一致性检查与故障定位")
    ap.add_argument("structure", help="table_scan 产物 structure.json")
    ap.add_argument("constraints", help="Agent 据数据字典填写的 constraints.json")
    ap.add_argument("--out-dir", default=".", help="输出目录（默认当前目录）")
    args = ap.parse_args(argv)

    try:
        structure = load_json(args.structure)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[consistency_check] 无法读取 structure.json: {e}", file=sys.stderr)
        return 2
    try:
        cfg = load_json(args.constraints)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[consistency_check] 无法读取 constraints.json: {e}", file=sys.stderr)
        return 2

    errors = validate_constraints(cfg, structure)
    if errors:
        print("[consistency_check] constraints.json 校验失败（退出码 4）:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 4

    cells = structure["cells"]
    header = structure["header"]
    row_labels = structure["row_labels"]

    builder = EquationBuilder(structure, cfg)
    eqs = builder.build()
    evaluate = make_evaluator(structure, cfg)
    for eq in eqs:
        status, expected, observed, tol, note = evaluate(eq)
        eq["status"] = status
        eq["expected"] = expected
        eq["observed"] = observed
        eq["tolerance"] = tol
        eq["abs_diff"] = (abs(observed - expected) if expected is not None else None)
        if note:
            eq["note"] = note

    # 字典界检查
    bound_records = []
    for item in cfg.get("bounds", []):
        c = item["column"]
        for ri in range(structure["n_rows"]):
            k = cell_key(ri, c)
            cell = cells.get(k, {})
            v = cell.get("value")
            if v is None:
                continue
            lo, hi = item.get("min"), item.get("max")
            bad = (lo is not None and v < lo) or (hi is not None and v > hi)
            if bad:
                bound_records.append({
                    "cell": k, "value": v, "min": lo, "max": hi,
                    "source": item.get("source", ""),
                })

    violated = [e for e in eqs if e["status"] == "VIOLATED"]
    passed = [e for e in eqs if e["status"] == "PASS"]

    # 单元格 → 参与等式计数
    cell_vio = Counter()
    cell_pass = Counter()
    cell_vio_ids = {}
    for e in eqs:
        for k in e["cells"]:
            if e["status"] == "VIOLATED":
                cell_vio[k] += 1
                cell_vio_ids.setdefault(k, []).append(e["id"])
            elif e["status"] == "PASS":
                cell_pass[k] += 1

    def cell_rc(k):
        c = cells[k]
        return (c["row"], c["col"])

    # 贪心最小命中集：覆盖最多未覆盖违反等式；平局时参与已通过等式更少者优先，再按 (行,列) 序
    uncovered = {e["id"] for e in violated}
    eq_by_id = {e["id"]: e for e in violated}
    primary = []
    while uncovered:
        cand = set()
        for eid in uncovered:
            cand.update(eq_by_id[eid]["cells"])
        best = min(
            cand,
            key=lambda k: (
                -sum(1 for eid in uncovered if k in eq_by_id[eid]["cells"]),
                cell_pass.get(k, 0),
                cell_rc(k),
            ),
        )
        primary.append(best)
        uncovered = {eid for eid in uncovered if best not in eq_by_id[eid]["cells"]}

    primary_set = set(primary)
    in_violated = set()
    for e in violated:
        in_violated.update(e["cells"])
    alternative_set = in_violated - primary_set
    bound_cells = {b["cell"] for b in bound_records}

    def confidence(k):
        vio = cell_vio.get(k, 0)
        bnd = 1 if k in bound_cells else 0
        if k in primary_set:
            if vio >= 1 and bnd:
                return "high"
            if vio >= 2 or bnd:
                return "medium"
            return "low"
        if k in alternative_set:
            return "low"
        if bnd:
            return "medium"
        return "clean"

    def klass(k):
        if k in primary_set:
            return "primary"
        if k in alternative_set:
            return "alternative"
        if k in bound_cells:
            return "bound_only"
        return "clean"

    # suspect_map.csv：全数值单元格
    numeric_keys = sorted(
        (k for k, c in cells.items() if c.get("value") is not None),
        key=cell_rc,
    )
    suspect_path = f"{args.out_dir}/suspect_map.csv"
    with open(suspect_path, "w", encoding="utf-8", newline="") as f:
        f.write("row_index,row_label,column_index,column_header,value,class,confidence,"
                "violated_equations,bound_violation,passed_equations,note\n")
        for k in numeric_keys:
            c = cells[k]
            ri, ci = c["row"], c["col"]
            cls = klass(k)
            conf = confidence(k)
            vio_ids = ";".join(cell_vio_ids.get(k, []))
            bnd = "yes" if k in bound_cells else "no"
            note = ""
            if cls == "alternative":
                note = "位于违反等式中但未被最小命中集选中（替代解释）"
            elif cls == "primary":
                note = "最小命中集成员（主要可疑单元格）"
            elif cls == "bound_only":
                note = "仅违反字典物理界"
            row = [
                str(ri),
                row_labels[ri].replace(",", "，"),
                str(ci),
                header[ci].replace(",", "，"),
                c["raw"],
                cls,
                conf,
                vio_ids,
                bnd,
                str(cell_pass.get(k, 0)),
                note,
            ]
            f.write(",".join(row) + "\n")

    # equations.jsonl
    eq_path = f"{args.out_dir}/equations.jsonl"
    with open(eq_path, "w", encoding="utf-8") as f:
        for e in eqs:
            f.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")

    # consistency_report.md
    L = []
    L.append("# 算术自洽一致性报告（consistency_check）")
    L.append("")
    L.append(f"- 表: `{structure['source_file']}`")
    L.append(f"- sha256: `{structure['sha256']}`")
    L.append(f"- 恒等式: 共 {len(eqs)} 条；通过 {len(passed)}，违反 {len(violated)}，"
             f"无法评估 {len(eqs) - len(passed) - len(violated)}")
    L.append(f"- 字典界检查: 违反 {len(bound_records)} 处")
    L.append(f"- 最小命中集（主要可疑单元格）: {len(primary)} 个")
    L.append("")
    L.append("## 逐等式裁决")
    L.append("")
    L.append("| 等式 | 类型 | 表达式 | 观测 | 期望 | 容差 | 差值 | 裁决 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for e in eqs:
        obs = fmt(e["observed"]) if e["observed"] is not None else "—"
        exp = fmt(e["expected"]) if e["expected"] is not None else "—"
        tol = fmt(e["tolerance"]) if e["tolerance"] is not None else "—"
        dif = fmt(e["abs_diff"]) if e["abs_diff"] is not None else "—"
        note = e.get("note", "")
        verdict = e["status"] + (f"（{note}）" if note else "")
        L.append(f"| {e['id']} | {e['type']} | `{e['expression']}` | {obs} | {exp} | {tol} | {dif} | {verdict} |")
    L.append("")
    if bound_records:
        L.append("## 字典界违反")
        L.append("")
        L.append("| 单元格 | 值 | 下界 | 上界 | 依据 |")
        L.append("|---|---|---|---|---|")
        for b in bound_records:
            L.append(f"| {b['cell']} | {fmt(b['value'])} | {fmt(b['min'])} | {fmt(b['max'])} | {b['source']} |")
        L.append("")
    L.append("## 故障定位（最小命中集）")
    L.append("")
    if not primary:
        L.append("未发现主要可疑单元格（无违反等式，或违反等式均无法评估）。")
    else:
        L.append("| 单元格 | 行 | 列 | 当前值 | 参与违反等式 | 参与通过等式 | 置信 |")
        L.append("|---|---|---|---|---|---|---|")
        for k in primary:
            c = cells[k]
            L.append(f"| {k} | R{c['row']} `{row_labels[c['row']]}` | C{c['col']} `{header[c['col']]}` "
                     f"| {c['raw']} | {cell_vio.get(k, 0)} | {cell_pass.get(k, 0)} | {confidence(k)} |")
        L.append("")
        L.append("说明：命中集是“能解释全部违反等式的最小单元格集合”的贪心解；"
                 "位于违反等式中但未被选中的单元格在 suspect_map.csv 中标为 alternative（替代解释），"
                 "恢复阶段只允许处理 primary 单元格。")
    L.append("")
    L.append("## 置信分级定义")
    L.append("")
    L.append("- high：主要可疑单元格，同时违反算术恒等式与字典物理界。")
    L.append("- medium：主要可疑单元格且参与 ≥2 条违反等式；或仅违反字典界。")
    L.append("- low：仅参与 1 条违反等式的孤立可疑单元格，或替代解释单元格。")
    L.append("- clean：未参与任何违反项。")
    L.append("")
    with open(f"{args.out_dir}/consistency_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"[consistency_check] 等式 {len(eqs)} 条: 通过 {len(passed)}, 违反 {len(violated)}; "
          f"字典界违反 {len(bound_records)}; 主要可疑单元格 {len(primary)} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
