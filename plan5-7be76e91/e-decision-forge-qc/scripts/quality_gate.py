#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""quality_gate.py — decision_package.json 过程质量门（decision-forge-qc）。

对决策包做确定性机检，拦截不可辩护的交付：
  1. 每个方案七类字段（assumptions/variables/controls/steps/parameters/
     resources/evaluation_criteria）每组非空，且条目带 id；
  2. 每条 elimination 必须有 rule + evidence_refs，且每个证据引用指向包内
     存在的条目（矩阵条目 id、"<plan_id>.<category>" 组引用或确认项 id）；
  3. confirmations 中 status=pending 的确认项，其 id 不得出现在
     selection.rationale / discarded_reasons 文本中（确认项隔离）；
     存在 pending 项时 selection.status 必须为 "provisional"（结论降级）；
  4. result_skeleton 含 case_id（与包内及 case.json 对账）且含
     case.json output_contract 的全部键（不漏键；允许额外键如
     status/sources/uncertainty）；
  5. scores 覆盖 weights 的全部维度，权重为正数。

退出码：0=通过；2=输入/用法错误；3=质量门拦截（缺陷清单打印到 stdout，
gate_report.json / gate_report.md 仍写出）。

仅使用 Python 标准库；输出确定性（不含时间戳/随机数），同一输入双跑产物
逐字节一致。
"""
import argparse
import json
import sys
from pathlib import Path

CATEGORIES = [
    "assumptions", "variables", "controls", "steps",
    "parameters", "resources", "evaluation_criteria",
]
CONF_KINDS = ["safety", "ethics", "equipment_availability", "expert"]
CONF_STATUSES = ["confirmed", "pending"]
SELECTION_STATUSES = ["final", "provisional"]


class InputError(Exception):
    """输入/用法错误（退出码 2）。"""


def load_json(path, what):
    p = Path(path)
    if not p.is_file():
        raise InputError(f"{what}不存在: {p}")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except UnicodeDecodeError as e:
        raise InputError(f"{what}不是合法 UTF-8: {p}: {e}")
    except json.JSONDecodeError as e:
        raise InputError(f"{what} JSON 解析失败: {p}: {e}")


def defect(defects, code, detail):
    defects.append({"code": code, "detail": detail})


def check_package(pkg, case, defects):
    """按固定顺序执行全部检查，保证缺陷清单顺序确定。"""
    if not isinstance(pkg, dict):
        defect(defects, "PACKAGE_NOT_OBJECT", "decision_package 顶层必须是 JSON 对象")
        return defects

    case_id = pkg.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip():
        defect(defects, "PACKAGE_CASE_ID_MISSING", "decision_package 缺少非空 case_id")
        case_id = None

    # ---- plans ------------------------------------------------------------
    plans = pkg.get("plans")
    plan_ids = []
    if not isinstance(plans, list) or not plans:
        defect(defects, "PLANS_MISSING", "plans 必须是非空数组")
    else:
        for i, plan in enumerate(plans):
            pid = plan.get("plan_id") if isinstance(plan, dict) else None
            if not isinstance(pid, str) or not pid.strip():
                defect(defects, "PLAN_ID_MISSING", f"plans[{i}] 缺少非空 plan_id")
            elif pid in plan_ids:
                defect(defects, "PLAN_ID_DUPLICATE", f"plan_id 重复: {pid}")
            else:
                plan_ids.append(pid)

    # ---- matrix 七类字段 ---------------------------------------------------
    matrix = pkg.get("matrix")
    evidence_ids = set()
    if not isinstance(matrix, dict):
        defect(defects, "MATRIX_MISSING", "matrix 必须是对象（键为 plan_id）")
        matrix = {}
    for pid in plan_ids:
        entry = matrix.get(pid)
        if not isinstance(entry, dict):
            defect(defects, "FIELD_GROUP_EMPTY",
                   f"方案 {pid} 在 matrix 中缺少七类字段对象")
            continue
        for cat in CATEGORIES:
            items = entry.get(cat)
            if not isinstance(items, list) or not items:
                defect(defects, "FIELD_GROUP_EMPTY",
                       f"方案 {pid} 的字段组 {cat} 缺失或为空")
                continue
            for j, item in enumerate(items):
                iid = item.get("id") if isinstance(item, dict) else None
                if not isinstance(iid, str) or not iid.strip():
                    defect(defects, "MATRIX_ENTRY_ID_MISSING",
                           f"方案 {pid} 字段组 {cat} 第 {j + 1} 条缺少 id")
                elif iid in evidence_ids:
                    defect(defects, "MATRIX_ENTRY_ID_DUPLICATE",
                           f"矩阵条目 id 重复: {iid}")
                else:
                    evidence_ids.add(iid)
        for cat in CATEGORIES:
            if isinstance(entry.get(cat), list) and entry[cat]:
                evidence_ids.add(f"{pid}.{cat}")

    # ---- confirmations -----------------------------------------------------
    confirmations = pkg.get("confirmations")
    pending_ids = []
    if not isinstance(confirmations, list):
        defect(defects, "CONFIRMATIONS_MISSING", "confirmations 必须是数组")
        confirmations = []
    for i, c in enumerate(confirmations):
        if not isinstance(c, dict):
            defect(defects, "CONFIRMATION_MALFORMED", f"confirmations[{i}] 不是对象")
            continue
        cid = c.get("id")
        if not isinstance(cid, str) or not cid.strip():
            defect(defects, "CONFIRMATION_ID_MISSING",
                   f"confirmations[{i}] 缺少非空 id")
            continue
        evidence_ids.add(cid)
        if c.get("kind") not in CONF_KINDS:
            defect(defects, "CONFIRMATION_KIND_UNKNOWN",
                   f"确认项 {cid} 的 kind 不在 {CONF_KINDS}: {c.get('kind')!r}")
        if c.get("status") not in CONF_STATUSES:
            defect(defects, "CONFIRMATION_STATUS_UNKNOWN",
                   f"确认项 {cid} 的 status 不在 {CONF_STATUSES}: {c.get('status')!r}")
        elif c["status"] == "pending":
            pending_ids.append(cid)

    # ---- eliminations ------------------------------------------------------
    eliminations = pkg.get("eliminations")
    if not isinstance(eliminations, list):
        defect(defects, "ELIMINATIONS_MISSING", "eliminations 必须是数组（可为空）")
        eliminations = []
    for i, e in enumerate(eliminations):
        if not isinstance(e, dict):
            defect(defects, "ELIMINATION_MALFORMED", f"eliminations[{i}] 不是对象")
            continue
        epid = e.get("plan_id")
        if epid not in plan_ids:
            defect(defects, "ELIMINATION_PLAN_UNKNOWN",
                   f"eliminations[{i}] 指向未知方案: {epid!r}")
        if not isinstance(e.get("rule"), str) or not e["rule"].strip():
            defect(defects, "ELIMINATION_RULE_MISSING",
                   f"eliminations[{i}]（方案 {epid}）缺少非空 rule")
        refs = e.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            defect(defects, "ELIMINATION_EVIDENCE_MISSING",
                   f"eliminations[{i}]（方案 {epid}）缺少 evidence_refs")
        else:
            for ref in refs:
                if not isinstance(ref, str) or ref not in evidence_ids:
                    defect(defects, "EVIDENCE_REF_UNKNOWN",
                           f"eliminations[{i}]（方案 {epid}）的证据引用在包内不存在: {ref!r}")

    # ---- selection：确认项隔离与降级 ----------------------------------------
    selection = pkg.get("selection")
    if not isinstance(selection, dict):
        defect(defects, "SELECTION_MISSING", "selection 必须是对象")
    else:
        sel_status = selection.get("status")
        if sel_status not in SELECTION_STATUSES:
            defect(defects, "SELECTION_STATUS_UNKNOWN",
                   f"selection.status 不在 {SELECTION_STATUSES}: {sel_status!r}")
        sel_plan = selection.get("selected_plan_id")
        if sel_plan is not None and sel_plan not in plan_ids:
            defect(defects, "SELECTION_PLAN_UNKNOWN",
                   f"selection.selected_plan_id 指向未知方案: {sel_plan!r}")
        texts = []
        if isinstance(selection.get("rationale"), str):
            texts.append(("selection.rationale", selection["rationale"]))
        else:
            defect(defects, "SELECTION_RATIONALE_MISSING",
                   "selection.rationale 缺失或不是字符串")
        dr = selection.get("discarded_reasons")
        if not isinstance(dr, list):
            defect(defects, "DISCARDED_REASONS_MISSING",
                   "selection.discarded_reasons 必须是数组")
        else:
            for j, d in enumerate(dr):
                if isinstance(d, dict) and isinstance(d.get("reason"), str):
                    texts.append((f"selection.discarded_reasons[{j}].reason", d["reason"]))
        for cid in pending_ids:
            for where, text in texts:
                if cid in text:
                    defect(defects, "SELECTION_CITES_PENDING",
                           f"{where} 引用了未确认（pending）确认项 {cid}；"
                           "未确认项不得写成已确认事实")
        if pending_ids and sel_status != "provisional":
            defect(defects, "SELECTION_NOT_PROVISIONAL",
                   f"存在 {len(pending_ids)} 个 pending 确认项 {pending_ids}，"
                   "selection.status 必须为 provisional（结论降级）")

    # ---- scores / weights 覆盖性 -------------------------------------------
    weights = pkg.get("weights")
    dims = []
    if not isinstance(weights, dict) or not weights:
        defect(defects, "WEIGHTS_MISSING", "weights 必须是非空对象")
    else:
        for d, w in weights.items():
            if not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0:
                defect(defects, "WEIGHTS_INVALID", f"权重 {d} 必须是正数: {w!r}")
            else:
                dims.append(d)
    scores = pkg.get("scores")
    if not isinstance(scores, dict):
        defect(defects, "SCORES_MISSING", "scores 必须是对象（键为 plan_id）")
    else:
        for pid in plan_ids:
            ps = scores.get(pid)
            if not isinstance(ps, dict):
                defect(defects, "SCORE_DIM_MISSING", f"方案 {pid} 缺少 scores")
                continue
            for d in dims:
                v = ps.get(d)
                if not isinstance(v, (int, float)) or isinstance(v, bool):
                    defect(defects, "SCORE_DIM_MISSING",
                           f"方案 {pid} 缺少维度 {d} 的数值评分")

    # ---- result_skeleton 对账 ----------------------------------------------
    skeleton = pkg.get("result_skeleton")
    if not isinstance(skeleton, dict):
        defect(defects, "RESULT_SKELETON_MISSING", "result_skeleton 必须是对象")
        skeleton = {}
    sk_case = skeleton.get("case_id")
    if not isinstance(sk_case, str) or not sk_case.strip():
        defect(defects, "SKELETON_CASE_ID_MISSING",
               "result_skeleton 缺少非空 case_id")
    elif case_id and sk_case != case_id:
        defect(defects, "SKELETON_CASE_ID_MISMATCH",
               f"result_skeleton.case_id={sk_case!r} 与包 case_id={case_id!r} 不一致")

    if case is not None:
        if not isinstance(case, dict):
            defect(defects, "CASE_NOT_OBJECT", "case.json 顶层必须是 JSON 对象")
        else:
            ccid = case.get("case_id")
            if case_id and isinstance(ccid, str) and ccid != case_id:
                defect(defects, "CASE_ID_MISMATCH",
                       f"包 case_id={case_id!r} 与 case.json case_id={ccid!r} 不一致")
            contract = case.get("output_contract")
            if not isinstance(contract, dict) or not contract:
                defect(defects, "OUTPUT_CONTRACT_MISSING",
                       "case.json 缺少非空 output_contract 对象")
            else:
                for key in sorted(contract.keys()):
                    if key not in skeleton:
                        defect(defects, "CONTRACT_KEY_MISSING",
                               f"result_skeleton 缺少 output_contract 键: {key!r}")
    return defects


def render_markdown(report):
    lines = []
    lines.append("# 质量门报告（decision-forge-qc / quality_gate.py）")
    lines.append("")
    lines.append(f"- case_id: {report['case_id']}")
    lines.append(f"- 结论: {'通过（PASS）' if report['passed'] else '拦截（FAIL）'}")
    lines.append(f"- 缺陷数: {report['defect_count']}")
    lines.append("")
    if report["defects"]:
        lines.append("| # | 缺陷代码 | 说明 |")
        lines.append("|---|---------|------|")
        for i, d in enumerate(report["defects"], 1):
            lines.append(f"| {i} | {d['code']} | {d['detail']} |")
    else:
        lines.append("未发现缺陷。")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="decision_package.json 过程质量门：七类字段完整性、淘汰证据引用、"
                    "确认项隔离与降级、result_skeleton 与 output_contract 对账。"
                    "退出码 0=通过 / 2=输入错误 / 3=质量门拦截（产物仍写出）。")
    ap.add_argument("--package", required=True, help="decision_package.json 路径")
    ap.add_argument("--case", default=None,
                    help="case.json 路径（提供时对账 case_id 与 output_contract 全部键）")
    ap.add_argument("--outdir", default=".",
                    help="gate_report.json / gate_report.md 输出目录（默认当前目录）")
    ap.add_argument("--note", default=None,
                    help="可选：嵌入 JSON/Markdown 产物顶部的标注（示例产物必须传合成示例标注）")
    args = ap.parse_args(argv)

    try:
        pkg = load_json(args.package, "决策包文件")
        case = load_json(args.case, "case 文件") if args.case else None
    except InputError as e:
        print(f"输入错误: {e}", file=sys.stderr)
        return 2

    defects = check_package(pkg, case, [])
    report = {
        "tool": "decision-forge-qc/quality_gate.py",
        "case_id": pkg.get("case_id") if isinstance(pkg, dict) else None,
        "passed": not defects,
        "defect_count": len(defects),
        "defects": defects,
    }
    if args.note is not None:
        report["note"] = args.note

    outdir = Path(args.outdir)
    try:
        outdir.mkdir(parents=True, exist_ok=True)
        with open(outdir / "gate_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        with open(outdir / "gate_report.md", "w", encoding="utf-8") as f:
            md_text = render_markdown(report)
            if args.note is not None:
                md_text = f"> {args.note}\n\n" + md_text
            f.write(md_text)
    except OSError as e:
        print(f"输入错误: 无法写出报告到 {outdir}: {e}", file=sys.stderr)
        return 2

    if defects:
        print(f"质量门拦截：{len(defects)} 个缺陷（gate_report.json 已写出）")
        for i, d in enumerate(defects, 1):
            print(f"  {i}. [{d['code']}] {d['detail']}")
        return 3
    print(f"质量门通过：0 个缺陷（case_id={report['case_id']}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
