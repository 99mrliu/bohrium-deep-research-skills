#!/usr/bin/env python3
"""render_ledger.py — 渲染 measurement-ledger.md / comparison-matrix.md / result.json 骨架。

输入:
  MEAS.jsonl              经 validate_measurements.py 机检通过的测量记录
  --kinds KINDS.json      quantity-kinds 登记表(默认 ../references/quantity-kinds.json)
  --case CASE.json        可选, 组织方 case.json; 用于复制 case_id 与 output_contract 字段名
  --workorder WO.json     可选, comparison-workorder.json; 记录比较任务
  --outdir DIR            输出目录(默认当前目录)

输出:
  measurement-ledger.md   台账: 按 quantity_kind 分组, 列: 原值|SI换算|单位|口径|条件窗|doc|paragraph|quote
  comparison-matrix.md    比较矩阵: 按 quantity_kind 分组的数值视图(原值列保留原文,
                          换算列一律标 derived), 六维度可比性结论
                          (metric/units 两维由单位代数自动判; task/material/pollutant/budget
                          由 agent 填写的 conditions 字段比对), 跨 quantity_kind 直接判不可比
  result.json             骨架: case_id 原样复制; output_contract 字段名原样照搬(值待填);
                          status/sources/uncertainty/comparability 预填机器可判部分

六维度: task, metric, units, material, pollutant, budget。
agent 在测量记录中以 "conditions": {"task":..., "material":..., "pollutant":..., "budget":...}
给出各维取值(取自 condition_context 的判读); 缺失维记 "unreported", 永不合并不同取值。
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from units import parse_unit, convertible, convert, dims_label  # noqa: E402

DEFAULT_KINDS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "..", "references", "quantity-kinds.json")
DIMS6 = ["task", "metric", "units", "material", "pollutant", "budget"]


def load_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def si_view(rec):
    """原值 × scale -> SI 基本单位视图字符串。"""
    p = parse_unit(rec.get("unit", "")) if rec.get("unit") else None
    if p is None:
        return "unregistered(不换算)"
    si_val = rec["value"] * p["scale"]
    return f"{si_val:.6g} [{dims_label(p['dimensions'])}] (derived)"


def group_by_kind(records):
    groups = {}
    for r in records:
        if r.get("status") == "excluded":
            continue
        groups.setdefault(r["quantity_kind"], []).append(r)
    return groups


def render_ledger(records, kinds, path):
    lines = ["# Measurement Ledger(测量台账)",
             "",
             "> 每格 = 一条测量记录: value + unit(解析为 SI 量纲向量与换算因子) + quantity_kind",
             "> + metric_definition(口径随值走) + condition_context + 逐字 quote + doc/paragraph。",
             "> SI 换算列一律为 derived; 原值原文保留。",
             ""]
    for kind, recs in sorted(group_by_kind(records).items()):
        kinfo = kinds["quantity_kinds"].get(kind, {})
        lines += [f"## {kind}",
                  "",
                  f"- 定义: {kinfo.get('definition', '(未登记)')}",
                  f"- 口径要求: {kinfo.get('metric_definition_required', '(未登记)')}",
                  "",
                  "| id | 原值 | SI 换算 | 单位 | 口径(metric_definition) | 条件窗 | doc | paragraph | quote |",
                  "|---|---|---|---|---|---|---|---|---|"]
        for r in recs:
            cond = r.get("condition_context", "")
            if isinstance(cond, dict):
                cond = "; ".join(f"{k}={v}" for k, v in cond.items())
            row = [r.get("measurement_id", ""),
                   f"{r.get('value_raw', r.get('value'))}",
                   si_view(r),
                   r.get("unit", ""),
                   str(r.get("metric_definition", "")).replace("|", "\\|"),
                   str(cond).replace("|", "\\|"),
                   r.get("document_id", ""),
                   r.get("paragraph_id", ""),
                   '"' + str(r.get("quote", "")).replace("|", "\\|") + '"']
            lines.append("| " + " | ".join(str(x) for x in row) + " |")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def dimension_verdicts(recs):
    """对同一 quantity_kind 组内记录做六维度可比性判定。返回 {dim: (verdict, detail)}。"""
    out = {}
    # units: 单位代数自动判
    parsed = [parse_unit(r["unit"]) for r in recs]
    if any(p is None for p in parsed):
        bad = [r["measurement_id"] for r, p in zip(recs, parsed) if p is None]
        out["units"] = ("unknown", f"存在不可解析单位: {bad}; 不换算, 保留原单位")
    else:
        d0 = parsed[0]["dimensions"]
        same = all(p["dimensions"] == d0 for p in parsed)
        if same:
            us = sorted({r["unit"] for r in recs})
            out["units"] = ("comparable",
                            f"量纲一致 {dims_label(d0)}; 单位写法 {us} 可互相换算(换算值标 derived)")
        else:
            out["units"] = ("not_comparable",
                            "量纲不一致: " + "; ".join(
                                f"{r['measurement_id']}={dims_label(p['dimensions'])}"
                                for r, p in zip(recs, parsed)))
    # metric: 口径自动比对(定义串一致性)
    mds = [str(r.get("metric_definition", "")).strip() for r in recs]
    if any(not m for m in mds):
        out["metric"] = ("unknown", "存在 metric_definition 缺失的记录(按规则不得进入比较)")
    elif len(set(mds)) == 1:
        out["metric"] = ("comparable", f"口径一致(auto): {mds[0][:80]}")
    else:
        out["metric"] = ("review",
                         "口径不一致(auto 标记, agent 复核): " +
                         "; ".join(f"{r['measurement_id']}: {m[:60]}" for r, m in zip(recs, mds)))
    # 其余四维: agent 填写的 conditions 字段比对
    for dim in ("task", "material", "pollutant", "budget"):
        vals = [str((r.get("conditions") or {}).get(dim, "")).strip() for r in recs]
        if any(not v for v in vals):
            missing = [r["measurement_id"] for r, v in zip(recs, vals) if not v]
            out[dim] = ("unknown", f"未报告: {missing}")
        elif len(set(vals)) == 1:
            out[dim] = ("comparable", f"取值一致: {vals[0]}")
        else:
            out[dim] = ("not_comparable",
                        "取值不同, 不得合并: " +
                        "; ".join(f"{r['measurement_id']}={v}" for r, v in zip(recs, vals)))
    return out


def render_matrix(records, kinds, workorder, path):
    lines = ["# Comparison Matrix(比较矩阵)",
             "",
             "> 按 quantity_kind 分组; **quantity_kind 不同的格子机检直接判不可比**;",
             "> 不同数据集/不同污染物(染料)不得合并; 不可比与未报告项保留在表中, 不删除。",
             ""]
    if workorder:
        lines += [f"比较任务: {workorder.get('task', workorder.get('comparison_task', '(未注明)'))}",
                  ""]
    groups = group_by_kind(records)
    for kind, recs in sorted(groups.items()):
        kinfo = kinds["quantity_kinds"].get(kind, {})
        canon = kinfo.get("canonical_unit")
        lines += [f"## 量类: {kind} (规范比较单位: {canon or '未登记'})", ""]
        lines.append("| measurement_id | doc | paragraph | 原值 | 单位 | 换算到规范单位 | 口径 | 六维可比性摘要 |")
        lines.append("|---|---|---|---|---|---|---|---|")
        verdicts = dimension_verdicts(recs)
        for r in recs:
            conv_cell = "(不可换算)"
            if canon:
                if r["unit"] == canon:
                    conv_cell = f"{r.get('value_raw', r['value'])} {canon} (reported)"
                else:
                    c = convert(r["value"], r["unit"], canon)
                    if c is not None:
                        conv_cell = f"{c['value']:.6g} {canon} (derived)"
            vsum = "; ".join(f"{d}:{v[0]}" for d, v in verdicts.items())
            lines.append("| " + " | ".join([
                r["measurement_id"], r["document_id"], r["paragraph_id"],
                str(r.get("value_raw", r["value"])), r["unit"], conv_cell,
                str(r.get("metric_definition", "")).replace("|", "\\|")[:60],
                vsum]) + " |")
        lines += ["", "### 六维度可比性判定", "",
                  "| 维度 | 结论 | 依据 |", "|---|---|---|"]
        for d in DIMS6:
            v, detail = verdicts[d]
            lines.append(f"| {d} | {v} | {detail.replace('|', '/')} |")
        lines.append("")
    # 跨量类不可比声明
    kinds_present = sorted(groups.keys())
    if len(kinds_present) > 1:
        lines += ["## 跨 quantity_kind 可比性(机检)", ""]
        for i in range(len(kinds_present)):
            for j in range(i + 1, len(kinds_present)):
                lines.append(f"- {kinds_present[i]} ↔ {kinds_present[j]}: **不可比**"
                             f" (quantity_kind 不同, 机检直接判不可比; 例如降解效率%与速率常数k不是同一个量)")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def render_result_skeleton(records, kinds, case, workorder, path):
    sources = sorted({r["document_id"] for r in records if r.get("status") != "excluded"})
    groups = group_by_kind(records)
    comparability = {}
    for kind, recs in sorted(groups.items()):
        comparability[kind] = {d: {"verdict": v, "detail": detail}
                               for d, (v, detail) in dimension_verdicts(recs).items()}
    cross = []
    ks = sorted(groups.keys())
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            cross.append({"pair": [ks[i], ks[j]], "verdict": "not_comparable",
                          "reason": "quantity_kind 不同, 机检直接判不可比"})
    case = case or {}
    case_id = case.get("case_id") or (workorder or {}).get("case_id") or "UNKNOWN"
    contract = case.get("output_contract")
    result = {"case_id": case_id}
    if isinstance(contract, dict):
        for k in contract.keys():  # 字段名原样照搬, 值待 agent 填
            result[k] = None
        result["_note_contract"] = "output_contract 字段名已原样照搬; 值由 agent 填写后删除本键"
    else:
        result["main_result"] = None
        result["_note_contract"] = "case.json 无 output_contract, 退化为 {case_id, status, 主结果, sources, uncertainty}"
    result["status"] = "partial"  # agent 完成后改 success; 无法完成写 failed; partial 须写明缺失边界
    result["sources"] = [{"document_id": d} for d in sources]
    result["comparability"] = {"by_quantity_kind": comparability, "cross_kind": cross,
                               "rule": "metric/units 两维由单位代数自动判; 其余四维由 conditions 比对; 未报告项保留"}
    result["uncertainty"] = "agent 待填: 抽取遗漏风险/口径歧义/换算精度; partial 必须写明缺失边界"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


def main(argv=None):
    ap = argparse.ArgumentParser(description="渲染台账/矩阵/result 骨架")
    ap.add_argument("measurements")
    ap.add_argument("--kinds", default=DEFAULT_KINDS)
    ap.add_argument("--case", default=None)
    ap.add_argument("--workorder", default=None)
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args(argv)

    with open(args.kinds, "r", encoding="utf-8") as f:
        kinds = json.load(f)
    records = load_jsonl(args.measurements)
    case = None
    if args.case and os.path.exists(args.case):
        with open(args.case, "r", encoding="utf-8") as f:
            case = json.load(f)
    workorder = None
    if args.workorder and os.path.exists(args.workorder):
        with open(args.workorder, "r", encoding="utf-8") as f:
            workorder = json.load(f)

    os.makedirs(args.outdir, exist_ok=True)
    p1 = os.path.join(args.outdir, "measurement-ledger.md")
    p2 = os.path.join(args.outdir, "comparison-matrix.md")
    p3 = os.path.join(args.outdir, "result.json")
    render_ledger(records, kinds, p1)
    render_matrix(records, kinds, workorder, p2)
    render_result_skeleton(records, kinds, case, workorder, p3)
    print(f"render_ledger: wrote {p1}, {p2}, {p3}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
