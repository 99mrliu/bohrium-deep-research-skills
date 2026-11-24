#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""contract_deliver.py — 契约先行的交付工具。

子命令：
  scaffold  解析 case.json 的 output_contract.required_fields，生成合法 partial 骨架
           （result.json + plan_skeleton.md）。缺 case.json 时用默认 9 字段集，不崩。
  fill      --field NAME --file content.json [--finalize-field]
            把某字段写入 result.json 并更新 fields_status（draft/final）。
  validate  机械验收：required_fields 非占位、case_id 一致、status 与 fields_status 自洽、
            plan.json 成本算术可重算、参数落在 parameter_domains 内。
            输出 validation_report.json；FAIL 时自动把 status 降为 partial 并写明缺口。
  render    plan.json + result.json -> plan.md（六要素 + 校验摘要表 + 确认项清单）；
            探测 pandoc/libreoffice，可用则导出 PDF，不可用在 uncertainty 如实记录。

仅 Python 3 标准库；确定性；缺键不崩（exit 0）；单次运行 <5 秒（PDF 导出除外）。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

DEFAULT_REQUIRED_FIELDS = [
    "case_id", "revised_plan", "candidate_assessment", "validation",
    "status", "uncertainty", "sources", "change_log", "confirmation_items",
]
VALID_STATUS = {"complete", "partial", "blocked"}
PLACEHOLDER_PREFIX = "<TODO:"

FIELD_TODOS = {
    "revised_plan": "修订方案六要素：假设与变量、对照组、设备材料、时间成本、参数范围、风险异常；参数须落在 case.parameter_domains 内",
    "candidate_assessment": "逐一评估 case.candidate_plans：算术复算、预约吞吐、参数域合规，指出每个候选的问题",
    "validation": "列出已做的机械校验（成本算术、参数域、时间可行性）及结论，可复算",
    "status": "由 validate 子命令机械维护，勿手填",
    "uncertainty": "如实列出不确定项与降级原因（如未生成 PDF 的原因）",
    "sources": "每个数字的来源：case.json 路径或标注为假设",
    "change_log": "交付过程的修改记录",
    "confirmation_items": "需委托方确认的事项（前瞻合同、未确认报价不得写成事实）",
}


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def is_placeholder(v):
    if v is None:
        return True
    if isinstance(v, str):
        s = v.strip()
        return s == "" or s.startswith(PLACEHOLDER_PREFIX)
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def placeholder(field):
    hint = FIELD_TODOS.get(field, "按 output_contract 要求填写")
    return "%s %s>" % (PLACEHOLDER_PREFIX, hint)


def get_required_fields(case):
    req = None
    if isinstance(case, dict):
        req = (case.get("output_contract") or {}).get("required_fields")
    if not req:
        req = list(DEFAULT_REQUIRED_FIELDS)
    req = list(dict.fromkeys(req))  # 去重保序
    for f in ("case_id", "status"):
        if f not in req:
            req.append(f)
    return req


# ---------------------------------------------------------------- scaffold
def cmd_scaffold(args):
    case = load_json(args.case) or {}
    case_id = case.get("case_id", "UNKNOWN_CASE")
    req = get_required_fields(case)
    os.makedirs(args.out, exist_ok=True)

    result = {"case_id": case_id, "status": "partial"}
    fields_status = {"case_id": "final", "status": "final"}
    for f in req:
        if f in ("case_id", "status"):
            continue
        result[f] = placeholder(f)
        fields_status[f] = "empty"
    # change_log 始终落成真实列表，便于 fill 追加
    result["change_log"] = ["scaffold: 初始化交付骨架，status=partial，字段占位待填"]
    fields_status["change_log"] = "draft" if "change_log" in req else "final"
    result["fields_status"] = fields_status

    result_path = os.path.join(args.out, "result.json")
    save_json(result_path, result)

    skel_path = os.path.join(args.out, "plan_skeleton.md")
    with open(skel_path, "w", encoding="utf-8") as f:
        f.write("# plan 骨架（六要素，待充实为 plan.json）\n\n")
        f.write("- case_id: %s\n- status: partial（保底合法交付已就位）\n\n" % case_id)
        for sec in ("1. 假设与变量", "2. 对照组", "3. 设备与材料",
                    "4. 时间与成本", "5. 参数范围", "6. 风险与异常"):
            f.write("## %s\n\n- TODO\n\n" % sec)
        f.write("## required_fields（来自 case.output_contract，缺失时为默认 9 字段）\n\n")
        for r in req:
            f.write("- %s\n" % r)

    print("[scaffold] result.json 骨架已写入 %s（status=partial，%d 个 required 字段）"
          % (result_path, len(req)))
    print("[scaffold] plan_skeleton.md 已写入 %s" % skel_path)
    print("[scaffold] 此刻起任何时刻被截断，都有一个合法的诚实 partial 可提交。")
    return 0


# ---------------------------------------------------------------- fill
def cmd_fill(args):
    result_path = os.path.join(args.out, "result.json")
    result = load_json(result_path)
    if result is None:
        print("[fill] 未找到 %s，请先运行 scaffold。" % result_path)
        return 0
    if args.field in ("case_id", "status"):
        print("[fill] 字段 %s 由工具机械维护，拒绝手填。" % args.field)
        return 0
    content = load_json(args.file)
    if content is None:
        print("[fill] 无法解析内容文件 %s（需为合法 JSON）。" % args.file)
        return 0
    result[args.field] = content
    fs = result.setdefault("fields_status", {})
    fs[args.field] = "final" if args.finalize_field else "draft"
    if isinstance(result.get("change_log"), list):
        result["change_log"].append(
            "fill: 字段 %s 写入并标记为 %s" % (args.field, fs[args.field]))
    save_json(result_path, result)
    print("[fill] %s -> %s（fields_status=%s）" % (args.file, args.field, fs[args.field]))
    if not args.finalize_field:
        print("[fill] 提示：确认无误后用 --finalize-field 标记 final，否则 validate 不予 complete。")
    return 0


# ---------------------------------------------------------------- validate
def check_value_in_domain(name, value, domain):
    errs = []
    vals = value if isinstance(value, list) else [value]
    t = domain.get("type")
    if t == "range":
        lo, hi, step = domain.get("min"), domain.get("max"), domain.get("step")
        for v in vals:
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                errs.append("%s=%r 非数值，无法对账 range 域" % (name, v))
                continue
            if lo is not None and v < lo:
                errs.append("%s=%s 低于域下限 %s" % (name, v, lo))
            if hi is not None and v > hi:
                errs.append("%s=%s 高于域上限 %s" % (name, v, hi))
            if step and lo is not None:
                q = (v - lo) / step
                if abs(q - round(q)) > 1e-9:
                    errs.append("%s=%s 不满足 step=%s（基于 min=%s）" % (name, v, step, lo))
    elif t == "enum":
        allowed = domain.get("values", [])
        for v in vals:
            if v not in allowed:
                errs.append("%s=%r 不在枚举域 %r 内" % (name, v, allowed))
    return errs


def cmd_validate(args):
    case = load_json(args.case) or {}
    req = get_required_fields(case)
    result_path = os.path.join(args.out, "result.json")
    result = load_json(result_path)
    checks = []

    if result is None:
        report = {"case_id": case.get("case_id", "UNKNOWN_CASE"),
                  "overall": "FAIL",
                  "checks": [{"id": "result_json", "status": "FAIL",
                              "detail": "result.json 缺失或不是合法 JSON",
                              "fix": "先运行 scaffold 生成骨架"}],
                  "fields_status": {}, "gaps": ["result.json 缺失"]}
        save_json(os.path.join(args.out, "validation_report.json"), report)
        print("[validate] FAIL: result.json 缺失，请先 scaffold。")
        return 0

    fs = result.get("fields_status") or {}

    # 1. required_fields 存在且非占位
    missing = [f for f in req if f not in result or is_placeholder(result.get(f))]
    checks.append({
        "id": "required_fields",
        "status": "PASS" if not missing else "FAIL",
        "detail": "全部 %d 个 required 字段存在且非占位" % len(req) if not missing
                  else "以下字段缺失或仍为占位: %s" % ", ".join(missing),
        "fix": "" if not missing else
               "对每个缺口字段：写内容 JSON 后用 `fill --field <名> --file <内容.json>` 填入",
    })

    # 2. case_id 一致
    cid_case = case.get("case_id")
    if cid_case is None:
        checks.append({"id": "case_id_match", "status": "SKIP",
                       "detail": "case.json 不可用或无 case_id，跳过一致性检查",
                       "fix": ""})
    else:
        ok = result.get("case_id") == cid_case
        checks.append({"id": "case_id_match",
                       "status": "PASS" if ok else "FAIL",
                       "detail": "result.case_id=%r 与 case.json 一致" % result.get("case_id") if ok
                                 else "result.case_id=%r != case.json case_id=%r" % (result.get("case_id"), cid_case),
                       "fix": "" if ok else "重新 scaffold 或手工把 result.case_id 改回 case.json 的 case_id"})

    # 3. 全部 required 字段 final
    not_final = [f for f in req if fs.get(f) != "final"]
    checks.append({
        "id": "fields_final",
        "status": "PASS" if not not_final else "FAIL",
        "detail": "全部 required 字段 fields_status=final" if not not_final
                  else "以下字段未 final: %s" % ", ".join("%s(%s)" % (f, fs.get(f, "缺失")) for f in not_final),
        "fix": "" if not not_final else
               "确认内容后用 `fill --field <名> --file <内容.json> --finalize-field` 标记 final",
    })

    # 4. status 自洽
    st = result.get("status")
    if st not in VALID_STATUS:
        checks.append({"id": "status_consistency", "status": "FAIL",
                       "detail": "status=%r 非法，应为 complete/partial/blocked" % st,
                       "fix": "status 由 validate 维护，运行 validate 即可自动纠正"})
    elif st == "complete" and not_final:
        checks.append({"id": "status_consistency", "status": "FAIL",
                       "detail": "status=complete 但存在未 final 字段: %s" % ", ".join(not_final),
                       "fix": "补 final 后重跑 validate；validate 会自动降级"})
    else:
        checks.append({"id": "status_consistency", "status": "PASS",
                       "detail": "status=%s 与 fields_status 自洽" % st, "fix": ""})

    # 5. plan.json 成本算术可重算
    plan = load_json(os.path.join(args.out, "plan.json"))
    if plan is None:
        checks.append({"id": "cost_arithmetic", "status": "FAIL",
                       "detail": "plan.json 缺失或非法，无法重算成本",
                       "fix": "把方案落为 plan.json（含 cost_items: [{item,unit_price,quantity,subtotal}] 与 total_cost）"})
    else:
        arith_errs = []
        items = plan.get("cost_items") or []
        subtotal_sum = 0.0
        for it in items:
            up, q, sub = it.get("unit_price"), it.get("quantity"), it.get("subtotal")
            if not all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (up, q, sub)):
                arith_errs.append("cost_item %r 缺 unit_price/quantity/subtotal 数值" % it.get("item"))
                continue
            if abs(up * q - sub) > 1e-6:
                arith_errs.append("%s: unit_price(%s)*quantity(%s)=%s != subtotal(%s)"
                                  % (it.get("item"), up, q, up * q, sub))
            subtotal_sum += sub
        total = plan.get("total_cost")
        if not isinstance(total, (int, float)) or isinstance(total, bool):
            arith_errs.append("total_cost 缺失或非数值")
        elif abs(subtotal_sum - total) > 1e-6:
            arith_errs.append("sum(subtotal)=%s != total_cost(%s)" % (subtotal_sum, total))
        checks.append({"id": "cost_arithmetic",
                       "status": "PASS" if not arith_errs else "FAIL",
                       "detail": "cost_items 与 total_cost 算术可重算（%d 项）" % len(items) if not arith_errs
                                 else "；".join(arith_errs),
                       "fix": "" if not arith_errs else "逐条按 unit_price*quantity 改 subtotal，并令 total_cost=sum(subtotal)"})

    # 6. 参数域合规（若 case 提供 parameter_domains）
    domains = case.get("parameter_domains") or {}
    if not domains:
        checks.append({"id": "parameter_domains", "status": "SKIP",
                       "detail": "case.json 未提供 parameter_domains，跳过", "fix": ""})
    else:
        param_errs = []
        sources = []
        rp = result.get("revised_plan")
        if isinstance(rp, dict) and isinstance(rp.get("parameters"), dict):
            sources.append(("revised_plan.parameters", rp["parameters"]))
        if isinstance(plan, dict) and isinstance(plan.get("parameters"), dict):
            sources.append(("plan.parameters", plan["parameters"]))
        if not sources:
            param_errs.append("未找到 revised_plan.parameters / plan.parameters，无法对账参数域")
        for label, params in sources:
            for k, v in params.items():
                if k in domains:
                    for e in check_value_in_domain("%s.%s" % (label, k), v, domains[k]):
                        param_errs.append(e)
        checks.append({"id": "parameter_domains",
                       "status": "PASS" if not param_errs else "FAIL",
                       "detail": "全部参数落在 parameter_domains 内" if not param_errs
                                 else "；".join(param_errs),
                       "fix": "" if not param_errs else "把越域参数改回域内，或在 uncertainty/confirmation_items 中说明"})

    overall = "PASS" if all(c["status"] in ("PASS", "SKIP") for c in checks) else "FAIL"
    gaps = ["[%s] %s" % (c["id"], c["detail"]) for c in checks if c["status"] == "FAIL"]

    # 诚实状态机械维护：PASS 才允许 complete；FAIL 自动降 partial 并写明缺口
    if overall == "PASS":
        result["status"] = "complete"
        result.pop("validation_gaps", None)
    else:
        result["status"] = "partial"
        result["validation_gaps"] = gaps
    save_json(result_path, result)

    report = {"case_id": result.get("case_id", case.get("case_id", "UNKNOWN_CASE")),
              "overall": overall, "checks": checks,
              "fields_status": fs, "gaps": gaps,
              "status_after_validate": result["status"],
              "generated_by": "contract_deliver.py validate"}
    report_path = os.path.join(args.out, "validation_report.json")
    save_json(report_path, report)
    print("[validate] overall=%s -> result.status=%s；报告: %s" % (overall, result["status"], report_path))
    for c in checks:
        print("  [%s] %s: %s" % (c["status"], c["id"], c["detail"]))
    if overall == "FAIL":
        print("[validate] 已自动把 status 降为 partial 并在 result.validation_gaps 写明缺口——诚实 partial 由脚本保证。")
    return 0


# ---------------------------------------------------------------- render
def md_block(content, indent=0):
    pad = "  " * indent
    lines = []
    if isinstance(content, list):
        for x in content:
            if isinstance(x, dict) and all(not isinstance(v, (list, dict)) for v in x.values()):
                lines.append(pad + "- " + "，".join("%s: %s" % (k, v) for k, v in x.items()))
            elif isinstance(x, (list, dict)):
                lines.append(md_block(x, indent + 1))
            else:
                lines.append(pad + "- %s" % x)
    elif isinstance(content, dict):
        for k, v in content.items():
            if isinstance(v, (list, dict)):
                lines.append(pad + "- **%s**:" % k)
                lines.append(md_block(v, indent + 1))
            else:
                lines.append(pad + "- **%s**: %s" % (k, v))
    else:
        lines.append(pad + "%s" % content)
    return "\n".join(lines)


def cmd_render(args):
    case = load_json(args.case) or {}
    result = load_json(os.path.join(args.out, "result.json")) or {}
    plan = load_json(os.path.join(args.out, "plan.json"))
    report = load_json(os.path.join(args.out, "validation_report.json"))

    L = []
    L.append("# 实验方案（人读渲染件）")
    L.append("")
    L.append("- case_id: %s" % result.get("case_id", case.get("case_id", "UNKNOWN_CASE")))
    L.append("- title: %s" % case.get("title", "（case.json 未提供）"))
    L.append("- status: %s" % result.get("status", "unknown"))
    if report:
        L.append("- validation: %s" % report.get("overall"))
    else:
        L.append("- validation: 尚未运行 validate（无 validation_report.json）")
    L.append("")

    plan_d = plan or {}
    if plan is None:
        L.append("> plan.json 缺失，以下章节待补；先写 plan.json 再 render。")
        L.append("")
    for title, content in [
        ("1. 假设与变量", plan_d.get("assumptions_variables") or plan_d.get("assumptions")),
        ("2. 对照组", plan_d.get("controls")),
        ("3. 设备与材料", plan_d.get("equipment_materials")),
    ]:
        L.append("## %s" % title)
        L.append("")
        L.append(md_block(content) if content else "- TODO")
        L.append("")

    # 时间与成本（含可重算成本表）
    L.append("## 4. 时间与成本")
    L.append("")
    if plan and plan.get("schedule"):
        L.append(md_block(plan["schedule"]))
        L.append("")
    items = (plan or {}).get("cost_items") or []
    if items:
        L.append("| 项目 | 单价 | 数量 | 小计 |")
        L.append("| --- | ---: | ---: | ---: |")
        for it in items:
            L.append("| %s | %s | %s | %s |" % (it.get("item"), it.get("unit_price"),
                                                 it.get("quantity"), it.get("subtotal")))
        L.append("| **合计** | | | **%s** |" % (plan or {}).get("total_cost"))
    else:
        L.append("- TODO: cost_items")
    L.append("")

    for title, content in [
        ("5. 参数范围", plan_d.get("parameters")),
        ("6. 风险与异常", plan_d.get("risks")),
    ]:
        L.append("## %s" % title)
        L.append("")
        L.append(md_block(content) if content else "- TODO")
        L.append("")

    # 校验摘要表
    L.append("## 校验摘要")
    L.append("")
    if report:
        L.append("- overall: **%s**（status_after_validate=%s）"
                 % (report.get("overall"), report.get("status_after_validate")))
        L.append("")
        L.append("| 检查项 | 结果 | 说明 |")
        L.append("| --- | --- | --- |")
        for c in report.get("checks", []):
            L.append("| %s | %s | %s |" % (c.get("id"), c.get("status"),
                                            str(c.get("detail")).replace("|", "\\|")))
    else:
        L.append("尚未运行 validate。")
    L.append("")

    # 确认项清单
    L.append("## 确认项清单（confirmation_items）")
    L.append("")
    ci = result.get("confirmation_items")
    if isinstance(ci, list) and ci:
        for x in ci:
            L.append("- [ ] %s" % x)
    else:
        L.append("- [ ] TODO")
    L.append("")

    md_path = os.path.join(args.out, "plan.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("[render] plan.md 已写入 %s" % md_path)

    # PDF 导出：探测 pandoc / libreoffice，不可用则如实记录，绝不谎报
    pdf_path = os.path.join(args.out, "plan.pdf")
    note = None
    pandoc = shutil.which("pandoc")
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    try:
        if pandoc:
            subprocess.run([pandoc, md_path, "-o", pdf_path], check=True,
                           timeout=60, capture_output=True)
            print("[render] 已通过 pandoc 导出 %s" % pdf_path)
        elif soffice:
            subprocess.run([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", args.out, md_path],
                           check=True, timeout=120, capture_output=True)
            print("[render] 已通过 libreoffice 导出 %s" % pdf_path)
        else:
            note = ("未生成 PDF 预览：运行环境未检测到 pandoc 或 libreoffice/soffice；"
                    "plan.md 为最终人读件，内容不因此缺失。")
    except Exception as e:
        note = "未生成 PDF 预览：导出工具调用失败（%s）；plan.md 为最终人读件。" % e
    if note:
        unc = result.get("uncertainty")
        if not isinstance(unc, list):
            unc = [] if is_placeholder(unc) else [unc]
        if note not in unc:
            unc.append(note)
        result["uncertainty"] = unc
        save_json(os.path.join(args.out, "result.json"), result)
        print("[render] %s（已如实记入 result.uncertainty）" % note)
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="契约先行的交付工具：scaffold(保底骨架) -> fill(逐字段) -> validate(机械验收) -> render(人读件)")
    p.add_argument("--case", default="/input/case.json", help="case.json 路径（默认 /input/case.json）")
    p.add_argument("--out", default="/app/output", help="交付目录（默认 /app/output）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scaffold", help="生成合法 partial 骨架 result.json + plan_skeleton.md")
    pf = sub.add_parser("fill", help="把某字段内容写入 result.json 并更新 fields_status")
    pf.add_argument("--field", required=True, help="字段名（case_id/status 由工具维护，拒绝手填）")
    pf.add_argument("--file", required=True, help="内容 JSON 文件路径")
    pf.add_argument("--finalize-field", action="store_true", help="标记该字段为 final")
    sub.add_parser("validate", help="机械验收并输出 validation_report.json；FAIL 自动降 partial")
    sub.add_parser("render", help="渲染 plan.md，并在 PDF 工具不可用时如实记录降级")
    args = p.parse_args(argv)
    return {"scaffold": cmd_scaffold, "fill": cmd_fill,
            "validate": cmd_validate, "render": cmd_render}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
