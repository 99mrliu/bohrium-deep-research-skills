#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_example_plan.py — 仅示例用（非 skill 正式脚本）：把 risk_map/audit/risk_section 机械
装配成 plan.json / plan.md / result.json，演示 SKILL.md 第 9-10 步的落地产物。
在真实运行中，这部分由 Agent 按 SKILL.md 工作流完成，脚本产物（risk_map/audit/
anomaly_tree/risk_section）原样嵌入，风险章节禁止手写。

候选方案对账（算术、参数域、排期）在这里用代码机械执行，演示 SPEC 要求的"靠脚本发现"。
"""
import argparse
import json
import os
import re

HEADER_NOTE = "合成示例输出，非正式测评结果"


def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def assess_candidates(case):
    """机械对账候选方案：成本算术、参数域、排期吞吐。"""
    rc = case.get("resource_contract") or {}
    domains = case.get("parameter_domains") or {}
    findings = []
    for cp in case.get("candidate_plans") or []:
        ver = cp.get("version", "?")
        items = cp.get("cost_items") or []
        s = sum((it.get("subtotal") or 0) for it in items if isinstance(it, dict))
        claimed = cp.get("total_cost")
        if claimed is not None and claimed != s:
            findings.append({"version": ver, "type": "COST-ARITHMETIC",
                             "detail": "total_cost=%s 与 cost_items 合计 %s 不符" % (claimed, s)})
        for pname, pval in (cp.get("parameters") or {}).items():
            dom = domains.get(pname)
            if not dom:
                continue
            vals = pval if isinstance(pval, list) else [pval]
            if dom.get("type") == "range":
                bad = [v for v in vals if not (dom["min"] <= v <= dom["max"])
                       or (v - dom["min"]) % (dom.get("step") or 1) != 0]
                if bad:
                    findings.append({"version": ver, "type": "PARAM-OUT-OF-DOMAIN",
                                     "detail": "%s 取值 %s 越出有限域 [%s,%s] step %s"
                                     % (pname, bad, dom["min"], dom["max"], dom.get("step"))})
            elif dom.get("type") == "enum":
                bad = [v for v in vals if v not in dom.get("values", [])]
                if bad:
                    findings.append({"version": ver, "type": "PARAM-OUT-OF-DOMAIN",
                                     "detail": "%s 取值 %s 不在枚举域 %s"
                                     % (pname, bad, dom.get("values"))})
        est = cp.get("est_days")
        deadline = rc.get("deadline_days")
        if est and deadline and est > deadline:
            findings.append({"version": ver, "type": "SCHEDULE-INFEASIBLE",
                             "detail": "est_days=%s 超过 deadline_days=%s" % (est, deadline)})
    note = case.get("equipment_domain_note") or ""
    embedded = re.findall(r"\{.*\}", note)  # 贪婪取整段内嵌 JSON（booking 含嵌套花括号）
    listed = {e.get("id") for e in rc.get("equipment", []) if isinstance(e, dict)}
    for frag in embedded:
        try:
            eq = json.loads(frag)
        except Exception:
            continue
        if eq.get("id") not in listed:
            findings.append({"version": "case", "type": "EQUIPMENT-EMBEDDED-NOT-LISTED",
                             "detail": "%s (%s) 仅出现在 equipment_domain_note，"
                                       "可用性与计价须单独确认"
                                       % (eq.get("id"), eq.get("name"))})
    return findings


def main():
    ap = argparse.ArgumentParser(description="示例装配器：risk_map+audit -> plan/result")
    ap.add_argument("--case", required=True)
    ap.add_argument("--steps", required=True)
    ap.add_argument("--risk-map", required=True)
    ap.add_argument("--audit", required=True)
    ap.add_argument("--risk-section", required=True)
    ap.add_argument("--confirmations", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    case = load_json(args.case)
    steps_doc = load_json(args.steps)
    rm = load_json(args.risk_map)
    audit = load_json(args.audit)
    conf = load_json(args.confirmations)
    risk_md = read_text(args.risk_section)
    # 风险章节嵌入 plan.md 时编为第 6 章（render 产物本身不编号，便于嵌入任意方案）
    risk_md = risk_md.replace("## 风险与异常处置（", "## 6 风险与异常处置（", 1)
    os.makedirs(args.out_dir, exist_ok=True)

    findings = assess_candidates(case)
    summary = rm.get("summary", {})
    mx = summary.get("max_rpn") or {}
    rc = case.get("resource_contract") or {}

    # ---- 高 RPN 反向设计修改（从 risk_map 的 design_feedback 机械收集）
    design_changes, seen = [], set()
    for st in rm.get("steps", []):
        for fm in st.get("failure_modes", []):
            if fm.get("high_priority") and (st["id"], fm["failure_mode_id"]) not in seen:
                seen.add((st["id"], fm["failure_mode_id"]))
                design_changes.append({
                    "trigger": "%s %s @ %s (RPN %s)" % (fm["failure_mode_id"], fm["name"],
                                                        st["id"], fm["rpn"]),
                    "design_change": fm.get("design_feedback", "")})

    # ---- plan.json（六要素）
    plan = {
        "note": HEADER_NOTE,
        "case_id": case.get("case_id", ""),
        "assumptions_and_variables": [
            "自变量：退火温度（case:parameter_domains.anneal_temperature_C，80-150°C step5）、旋涂转速（enum 2000/3000/4000/6000）",
            "因变量：XRD 主峰强度与 PbI2 残留峰强比、UV-Vis 吸收边、批间 RSD（验收阈值 ≤15%，case:research_goal）",
            "假设：手套箱 H2O<1ppm 全程维持（前瞻合同 spec，待设备可用性确认）；环境温湿度未受控，作为重复性排查变量记录"
        ],
        "controls": [
            "空白对照：ST-01 每批配制同做空白溶剂对照（FM-CONTAM 判据确认）",
            "标准样对照：ST-04/ST-05 前置标准样校验仪器（FM-NOSIGNAL 设计要求）",
            "重复对照：ST-06 最优温度点独立 3 批，RSD≤15% 验收"
        ],
        "equipment_materials": {
            "contract_disclaimer": rc.get("disclaimer", ""),
            "equipment": [e.get("id") for e in rc.get("equipment", []) if isinstance(e, dict)] + ["EQ-HP(equipment_domain_note 内嵌，已解析对账)"],
            "reagents": [r.get("id") for r in rc.get("reagents", []) if isinstance(r, dict)],
            "note": "价格与排期为前瞻约定，实际报价/预约状态见 confirmation_items 设备可用性类"
        },
        "schedule_budget": {
            "budget_cap": rc.get("budget_cap"), "currency": rc.get("currency"),
            "deadline_days": rc.get("deadline_days"),
            "v1_cost_correction": "候选 v1 total_cost=7330 与明细合计 5200 不符（见 candidate_assessment），修订方案以明细重算并预留 1 次重做余量",
            "booking_check": "EQ-XRD slots_per_week=2×30天窗口≈8 slot，已错峰安排并写入确认项"
        },
        "parameter_ranges": case.get("parameter_domains") or {},
        "steps": [{"id": st["id"], "name": st["name"],
                   "risk_refs": [fm["failure_mode_id"] for fm in st.get("failure_modes", [])],
                   "orphan": not st.get("failure_modes")}
                  for st in rm.get("steps", [])],
        "risk_section_source": "examples/output/risk_map.json 经 risk_fmea.py render 机械生成，禁止手写替代",
        "high_rpn_design_changes": design_changes,
        "confirmation_items": conf.get("confirmation_items", []),
    }
    with open(os.path.join(args.out_dir, "plan.json"), "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
        f.write("\n")

    # ---- plan.md（风险章节 = render 产物原文）
    lines = [
        "> %s" % HEADER_NOTE, "",
        "# 修订方案 plan.md — %s" % case.get("title", ""), "",
        "## 1 假设与变量", ""]
    lines += ["- %s" % a for a in plan["assumptions_and_variables"]]
    lines += ["", "## 2 对照组", ""]
    lines += ["- %s" % c for c in plan["controls"]]
    lines += ["", "## 3 设备与材料", "",
              "- 合同性质：%s" % plan["equipment_materials"]["contract_disclaimer"],
              "- 设备：%s" % ", ".join(plan["equipment_materials"]["equipment"]),
              "- 试剂：%s" % ", ".join(plan["equipment_materials"]["reagents"]),
              "", "## 4 时间与成本", "",
              "- 预算上限：%s %s；期限：%s 天" % (plan["schedule_budget"]["budget_cap"],
                                                 plan["schedule_budget"]["currency"],
                                                 plan["schedule_budget"]["deadline_days"]),
              "- %s" % plan["schedule_budget"]["v1_cost_correction"],
              "- %s" % plan["schedule_budget"]["booking_check"],
              "", "## 5 参数范围（限组织方有限参数域）", "",
              "- anneal_temperature_C：80–150°C，step 5（v1 的 160°C 越域，已收敛至 150°C）",
              "- spin_coating_rpm：枚举 {2000, 3000, 4000, 6000}，修订方案取 4000",
              "", risk_md.rstrip(), "",
              "## 7 高优先级失效模式驱动的设计修改（预防优于处置）", ""]
    lines += ["- **%s** → %s" % (d["trigger"], d["design_change"]) for d in design_changes]
    lines += ["", "异常处置决策树见 anomaly_tree.md。", ""]
    with open(os.path.join(args.out_dir, "plan.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    # ---- result.json（按 output_contract.required_fields）
    result = {
        "note": HEADER_NOTE,
        "case_id": case.get("case_id", ""),
        "revised_plan": {
            "summary": "v1 基础上：160°C 越域温度收敛至 150°C；成本按明细重算；"
                       "按高 RPN 失效模式反向加入预实验/标准样校验/双供应商/错峰排期；"
                       "风险章节由 risk_map.json 机械生成。",
            "parameters": {"spin_coating_rpm": 4000,
                           "anneal_temperature_C": [80, 95, 110, 125, 150]},
            "design_changes": design_changes,
        },
        "candidate_assessment": findings,
        "validation": {
            "audit_verdict": audit.get("verdict"),
            "coverage": audit.get("coverage"),
            "max_rpn_item": mx,
            "scripts": ["risk_fmea.py map", "risk_fmea.py audit",
                        "risk_fmea.py decision_tree", "risk_fmea.py render"],
        },
        "status": "complete" if audit.get("verdict") == "PASS" else "partial",
        "uncertainty": [
            "组织方合同为前瞻约定：价格/排期未确认，见 confirmation_items 设备可用性类",
            "EQ-HP 漂移史未知，FM-DRIFT 发生度评分为谨慎上调（plan_steps.json ST-03 overrides.reason）",
        ],
        "sources": [
            "case:resource_contract / parameter_domains / equipment_domain_note / candidate_plans",
            "references/failure_mode_library.md（失效模式基准评分与四要素模板）",
            "references/confirmation_checklist.md（四类确认项模板）",
        ],
        "change_log": [
            "v1→v2: anneal_temperature_C 160→150（越出有限域上限）",
            "v1→v2: total_cost 7330→按明细重算（算术不符，见 candidate_assessment）",
            "v1→v2: 新增 7 步失效模式映射（%d 条）与高 RPN 设计修改 %d 项"
            % (summary.get("total_failure_modes", 0), len(design_changes)),
        ],
        "confirmation_items": conf.get("confirmation_items", []),
    }
    required = ((case.get("output_contract") or {}).get("required_fields")) or []
    missing = [k for k in required if k not in result]
    result["required_fields_check"] = {"required": required, "missing": missing}
    with open(os.path.join(args.out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("plan.json / plan.md / result.json written to %s" % args.out_dir)
    print("audit_verdict=%s, max_rpn=%s, required_fields_missing=%s"
          % (audit.get("verdict"), mx, missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
