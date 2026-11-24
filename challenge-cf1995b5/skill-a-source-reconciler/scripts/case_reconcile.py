#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
case_reconcile.py — exp-source-reconciler 的核心机械脚本。

子命令：
  extract    解析 case.json → facts.json + facts.md（事实登记表，含文本内嵌补充解析）
  reconcile  机械对账（算术/参数域/合同覆盖/预算周期/依据定位）→ reconcile_report.json
  pdfscan    扫描输入目录下 PDF（pdftotext）→ pdf_excerpts.md（带真实页码，不可用时如实报告）

约束：仅 Python 3 标准库；确定性输出；缺键/坏文件不崩（exit 0，输出 partial 报告）；
支持 --help；单次运行 <5 秒。
"""
import argparse
import ast
import json
import math
import os
import re
import shutil
import subprocess
import sys

NOTICE = ""  # 示例输出头部标注由 run_example.sh 注入，脚本本身保持通用

SOURCE_CLASSES = [
    "case_meta", "contract", "parameter_domain",
    "candidate_claim", "literature", "text_embedded", "inferred",
]


# ---------------------------------------------------------------- 通用工具

def load_json(path):
    """读取 JSON，失败返回 ({}, error_str)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except Exception as e:  # noqa: BLE001
        return {}, "%s: %s" % (type(e).__name__, e)


def write_text(path, text):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def write_json(path, obj):
    write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def num_eq(a, b, tol=1e-6):
    return is_num(a) and is_num(b) and abs(a - b) <= tol


def fmt_num(x):
    if is_num(x) and float(x).is_integer():
        return str(int(x))
    return repr(x)


def md_escape(v):
    s = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    return s.replace("|", "\\|").replace("\n", " ")


def resolve_case_path(case, ref):
    """解析 'case:a.b[0].c' 形式的内部引用，返回 (ok, detail)。"""
    if not isinstance(ref, str) or not ref.startswith("case:"):
        return False, "不是 case: 前缀的内部引用"
    tokens = re.findall(r"\[\d+\]|[^.\[\]]+", ref[len("case:"):])
    cur = case
    for tok in tokens:
        if tok.startswith("["):
            idx = int(tok[1:-1])
            if isinstance(cur, list) and 0 <= idx < len(cur):
                cur = cur[idx]
            else:
                return False, "索引 %s 越界或目标不是列表" % tok
        else:
            if isinstance(cur, dict) and tok in cur:
                cur = cur[tok]
            else:
                return False, "键 '%s' 不存在" % tok
    return True, "已定位"


def extract_embedded_dicts(text):
    """从自由文本中抽取平衡花括号片段，依次尝试 json / python-literal 解析成 dict。"""
    if not isinstance(text, str):
        return []
    frags, depth, start = [], 0, None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                frags.append(text[start:i + 1])
                start = None
    out = []
    for frag in frags:
        obj = None
        for parser in (json.loads, ast.literal_eval):
            try:
                cand = parser(frag)
                if isinstance(cand, dict):
                    obj = cand
                    break
            except Exception:  # noqa: BLE001
                continue
        if obj is not None:
            out.append(obj)
    return out


# ---------------------------------------------------------------- extract

def extract_facts(case):
    """把 case.json 摊平成事实登记表。返回 (facts, equipment_table)。"""
    facts = []

    def add(value, unit, jsonpath, source_class, note=""):
        facts.append({
            "id": "F%03d" % (len(facts) + 1),
            "value": value,
            "unit": unit,
            "jsonpath": jsonpath,
            "source_class": source_class,
            "note": note,
        })

    # 1) 案例元信息
    for k in ("case_id", "title", "task", "research_goal", "note"):
        if k in case:
            add(case[k], None, k, "case_meta")

    # 2) 文献来源
    src = case.get("source") if isinstance(case.get("source"), dict) else {}
    for k in ("paper_pdf", "citation", "key_claim"):
        if k in src:
            add(src[k], None, "source." + k, "literature")

    # 3) 资源合同（前瞻约定，非已确认报价）
    rc = case.get("resource_contract") if isinstance(case.get("resource_contract"), dict) else {}
    for k in ("disclaimer", "currency"):
        if k in rc:
            add(rc[k], None, "resource_contract." + k, "contract")
    if "budget_cap" in rc:
        add(rc["budget_cap"], rc.get("currency"), "resource_contract.budget_cap", "contract",
            "预算上限（前瞻约定）")
    if "deadline_days" in rc:
        add(rc["deadline_days"], "day", "resource_contract.deadline_days", "contract", "周期上限")

    equipment_table = []
    for i, eq in enumerate(rc.get("equipment") or []):
        if not isinstance(eq, dict):
            continue
        base = "resource_contract.equipment[%d]" % i
        for k in ("id", "name", "model", "spec"):
            if k in eq:
                add(eq[k], None, "%s.%s" % (base, k), "contract")
        if "price_per_hour" in eq:
            add(eq["price_per_hour"], "%s/h" % rc.get("currency", "CNY"),
                base + ".price_per_hour", "contract", "前瞻约定价，非已确认报价")
        bk = eq.get("booking") if isinstance(eq.get("booking"), dict) else {}
        for k, unit in (("window_days", "day"), ("slots_per_week", "slot/week"), ("slot_hours", "h")):
            if k in bk:
                add(bk[k], unit, "%s.booking.%s" % (base, k), "contract", "预约吞吐参数（计划性约定）")
        equipment_table.append({
            "id": eq.get("id"), "name": eq.get("name"), "model": eq.get("model"),
            "spec": eq.get("spec"), "price_per_hour": eq.get("price_per_hour"),
            "booking": bk or None, "origin": "contract", "jsonpath": base,
        })

    for i, rg in enumerate(rc.get("reagents") or []):
        if not isinstance(rg, dict):
            continue
        base = "resource_contract.reagents[%d]" % i
        for k in ("id", "name", "spec", "unit", "pack_size"):
            if k in rg:
                add(rg[k], None, "%s.%s" % (base, k), "contract")
        if "unit_price" in rg:
            add(rg["unit_price"], "%s/%s" % (rc.get("currency", "CNY"), rg.get("unit", "?")),
                base + ".unit_price", "contract", "前瞻约定价，非已确认报价")

    # 4) 有限参数域
    pd = case.get("parameter_domains") if isinstance(case.get("parameter_domains"), dict) else {}
    for name, dom in pd.items():
        if not isinstance(dom, dict):
            continue
        base = "parameter_domains." + name
        unit = dom.get("unit")
        if dom.get("type") == "enum":
            add(dom.get("values"), unit, base + ".values", "parameter_domain", "枚举域")
        else:
            add({k: dom.get(k) for k in ("min", "max", "step") if k in dom},
                unit, base, "parameter_domain", "区间域")
        if dom.get("basis"):
            add(dom["basis"], None, base + ".basis", "parameter_domain", "参数域依据类别")
        if dom.get("source"):
            add(dom["source"], None, base + ".source", "parameter_domain", "参数域依据定位路径")

    # 5) 文本内嵌补充（如 equipment_domain_note 中内嵌的 JSON/dict 设备片段）
    for field in ("equipment_domain_note",):
        text = case.get(field)
        if not text:
            continue
        add(text, None, field, "contract", "自由文本，可能内嵌补充设备片段")
        for j, obj in enumerate(extract_embedded_dicts(text)):
            ebase = "%s~embedded[%d]" % (field, j)
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    add(v, None, "%s.%s" % (ebase, k), "text_embedded", "文本内嵌补充")
                else:
                    unit = ("%s/h" % rc.get("currency", "CNY")) if k == "price_per_hour" else None
                    add(v, unit, "%s.%s" % (ebase, k), "text_embedded", "文本内嵌补充")
            if "id" in obj or "name" in obj:
                equipment_table.append({
                    "id": obj.get("id"), "name": obj.get("name"), "model": obj.get("model"),
                    "spec": obj.get("spec"), "price_per_hour": obj.get("price_per_hour"),
                    "booking": obj.get("booking"), "origin": "text_embedded", "jsonpath": ebase,
                })

    # 6) 候选方案宣称（不可信，待对账）
    for i, plan in enumerate(case.get("candidate_plans") or []):
        if not isinstance(plan, dict):
            continue
        ver = plan.get("version", "v%d" % (i + 1))
        base = "candidate_plans[%d]" % i
        if plan.get("summary"):
            add(plan["summary"], None, base + ".summary", "candidate_claim", "版本 %s" % ver)
        params = plan.get("parameters") if isinstance(plan.get("parameters"), dict) else {}
        for pname, pval in params.items():
            add(pval, None, "%s.parameters.%s" % (base, pname), "candidate_claim",
                "候选 %s 宣称参数" % ver)
        for j, ci in enumerate(plan.get("cost_items") or []):
            if not isinstance(ci, dict):
                continue
            for k in ("item", "unit_price", "quantity", "subtotal"):
                if k in ci:
                    unit = rc.get("currency") if k in ("unit_price", "subtotal") else None
                    add(ci[k], unit, "%s.cost_items[%d].%s" % (base, j, k), "candidate_claim",
                        "候选 %s 成本行" % ver)
        if "total_cost" in plan:
            add(plan["total_cost"], rc.get("currency"), base + ".total_cost", "candidate_claim",
                "候选 %s 宣称总价" % ver)
        if "est_days" in plan:
            add(plan["est_days"], "day", base + ".est_days", "candidate_claim",
                "候选 %s 宣称周期" % ver)

    # 7) 输出契约
    oc = case.get("output_contract") if isinstance(case.get("output_contract"), dict) else {}
    if oc.get("required_fields"):
        add(oc["required_fields"], None, "output_contract.required_fields", "case_meta",
            "result.json 必含字段")

    return facts, equipment_table


def render_facts_md(case, facts, equipment_table):
    lines = []
    lines.append("# 事实登记表（fact registry）")
    lines.append("")
    lines.append("- case_id: %s" % case.get("case_id", "<missing>"))
    lines.append("- 生成器: scripts/case_reconcile.py extract（确定性机械提取）")
    lines.append("- 事实总数: %d" % len(facts))
    lines.append("- 来源类别: %s" % ", ".join(SOURCE_CLASSES))
    lines.append("")
    lines.append("## 统一设备表（合同 equipment 列表 + 文本内嵌补充合并）")
    lines.append("")
    lines.append("| id | name | model | price_per_hour | origin | jsonpath |")
    lines.append("|---|---|---|---|---|---|")
    for eq in equipment_table:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            md_escape(eq.get("id")), md_escape(eq.get("name")), md_escape(eq.get("model")),
            md_escape(eq.get("price_per_hour")), md_escape(eq.get("origin")),
            md_escape(eq.get("jsonpath"))))
    lines.append("")
    lines.append("## 事实明细（按来源类别分组）")
    for cls in SOURCE_CLASSES:
        group = [f for f in facts if f["source_class"] == cls]
        if not group:
            continue
        lines.append("")
        lines.append("### %s（%d 条）" % (cls, len(group)))
        lines.append("")
        lines.append("| id | value | unit | jsonpath | note |")
        lines.append("|---|---|---|---|---|")
        for f in group:
            lines.append("| %s | %s | %s | %s | %s |" % (
                f["id"], md_escape(f["value"]), md_escape(f["unit"]),
                md_escape(f["jsonpath"]), md_escape(f["note"])))
    lines.append("")
    return "\n".join(lines)


def cmd_extract(args):
    case, err = load_json(args.case)
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    if err:
        report = {"case_id": None, "partial": True, "errors": [err], "facts": [],
                  "equipment_table": []}
        write_json(os.path.join(outdir, "facts.json"), report)
        write_text(os.path.join(outdir, "facts.md"),
                   "# 事实登记表\n\n**partial**: case.json 读取失败: %s\n" % err)
        print("[extract] partial: %s" % err)
        return 0
    facts, eq_table = extract_facts(case)
    payload = {
        "case_id": case.get("case_id"),
        "generated_by": "scripts/case_reconcile.py extract",
        "fact_count": len(facts),
        "partial": False,
        "errors": [],
        "facts": facts,
        "equipment_table": eq_table,
    }
    write_json(os.path.join(outdir, "facts.json"), payload)
    write_text(os.path.join(outdir, "facts.md"), render_facts_md(case, facts, eq_table))
    n_emb = sum(1 for e in eq_table if e.get("origin") == "text_embedded")
    print("[extract] %d facts, %d equipment (%d text-embedded) -> %s"
          % (len(facts), len(eq_table), n_emb, outdir))
    return 0


# ---------------------------------------------------------------- reconcile

def build_known_items(case, equipment_table):
    """合同设备+试剂+文本内嵌设备 的统一可查表。"""
    known = []
    for eq in equipment_table:
        known.append({"id": eq.get("id"), "name": eq.get("name"),
                      "kind": "equipment", "origin": eq.get("origin"),
                      "price_per_hour": eq.get("price_per_hour"),
                      "booking": eq.get("booking")})
    rc = case.get("resource_contract") if isinstance(case.get("resource_contract"), dict) else {}
    for rg in rc.get("reagents") or []:
        if isinstance(rg, dict):
            known.append({"id": rg.get("id"), "name": rg.get("name"), "kind": "reagent",
                          "origin": "contract", "unit_price": rg.get("unit_price"),
                          "unit": rg.get("unit")})
    return known


def match_known(item, known):
    if item is None:
        return None
    needle = str(item).strip().lower()
    for k in known:
        for alias in (k.get("id"), k.get("name")):
            if not alias:
                continue
            a = str(alias).strip().lower()
            if a and (a in needle or needle in a):
                return k
    return None


def reconcile(case):
    checks = []

    def add(check_id, category, status, description, evidence, version=None):
        checks.append({"check_id": check_id, "category": category, "status": status,
                       "candidate_version": version, "description": description,
                       "evidence": evidence})

    rc = case.get("resource_contract") if isinstance(case.get("resource_contract"), dict) else {}
    pd = case.get("parameter_domains") if isinstance(case.get("parameter_domains"), dict) else {}
    plans = [p for p in (case.get("candidate_plans") or []) if isinstance(p, dict)]
    _, eq_table = extract_facts(case)
    known = build_known_items(case, eq_table)
    budget = rc.get("budget_cap")
    deadline = rc.get("deadline_days")
    cur = rc.get("currency", "CNY")

    # (a) 成本算术
    for i, plan in enumerate(plans):
        ver = plan.get("version", "v%d" % (i + 1))
        base = "candidate_plans[%d]" % i
        subtotal_sum = 0.0
        sum_ok = True
        for j, ci in enumerate(plan.get("cost_items") or []):
            if not isinstance(ci, dict):
                continue
            up, q, st = ci.get("unit_price"), ci.get("quantity"), ci.get("subtotal")
            jp = "%s.cost_items[%d]" % (base, j)
            if is_num(up) and is_num(q) and is_num(st):
                expect = round(up * q, 6)
                if num_eq(expect, st):
                    add("A-row", "cost_arithmetic", "PASS",
                        "成本行 unit_price×quantity == subtotal",
                        "%s: %s×%s=%s == subtotal %s" % (jp, fmt_num(up), fmt_num(q),
                                                         fmt_num(expect), fmt_num(st)), ver)
                else:
                    add("A-row", "cost_arithmetic", "FAIL",
                        "成本行 subtotal 算术错误",
                        "%s: %s×%s=%s ≠ subtotal %s（差额 %s）"
                        % (jp, fmt_num(up), fmt_num(q), fmt_num(expect), fmt_num(st),
                           fmt_num(round(st - expect, 6))), ver)
                subtotal_sum += st
            else:
                add("A-row", "cost_arithmetic", "WARN",
                    "成本行缺少数值字段，无法机械校验",
                    "%s: unit_price=%r quantity=%r subtotal=%r" % (jp, up, q, st), ver)
                sum_ok = False
        total = plan.get("total_cost")
        if is_num(total) and sum_ok and (plan.get("cost_items") is not None):
            s = round(subtotal_sum, 6)
            formula = "+".join(fmt_num(ci.get("subtotal"))
                               for ci in (plan.get("cost_items") or [])
                               if isinstance(ci, dict) and is_num(ci.get("subtotal")))
            if num_eq(s, total):
                add("A-total", "cost_arithmetic", "PASS",
                    "各行 subtotal 之和 == total_cost",
                    "%s.total_cost: %s = %s == total_cost %s" % (base, formula, fmt_num(s),
                                                                 fmt_num(total)), ver)
            else:
                add("A-total", "cost_arithmetic", "FAIL",
                    "total_cost 与各行之和不符",
                    "%s.total_cost: %s = %s ≠ 宣称 total_cost %s（差额 %s %s）"
                    % (base, formula, fmt_num(s), fmt_num(total),
                       fmt_num(round(total - s, 6)), cur), ver)
        elif not is_num(total):
            add("A-total", "cost_arithmetic", "WARN", "候选缺少 total_cost，无法校验合计",
                "%s.total_cost=%r" % (base, total), ver)

    # (b) 参数 vs 有限参数域
    def check_value_in_domain(pname, v, dom, jp, ver):
        unit = dom.get("unit") or ""
        if dom.get("type") == "enum":
            vals = dom.get("values") or []
            ok = any(num_eq(v, ev) for ev in vals)
            if ok:
                add("B-param", "parameter_domain", "PASS",
                    "参数值落在枚举域内",
                    "%s=%s ∈ %s %s" % (jp, fmt_num(v), vals, unit), ver)
            else:
                add("B-param", "parameter_domain", "FAIL",
                    "参数值越出枚举域",
                    "%s=%s ∉ 枚举域 %s %s（越域）" % (jp, fmt_num(v), vals, unit), ver)
        else:
            mn, mx, step = dom.get("min"), dom.get("max"), dom.get("step")
            if is_num(mn) and is_num(mx) and not (mn <= v <= mx):
                add("B-param", "parameter_domain", "FAIL",
                    "参数值越出区间域",
                    "%s=%s 不在 [%s, %s] %s 内（越域）" % (jp, fmt_num(v), fmt_num(mn),
                                                          fmt_num(mx), unit), ver)
                return
            if is_num(step) and step and is_num(mn):
                k = (v - mn) / step
                if abs(k - round(k)) > 1e-9:
                    add("B-param", "parameter_domain", "WARN",
                        "参数值落在区间内但不落在 step 网格上",
                        "%s=%s，min=%s step=%s%s，(v-min)/step=%s 非整数"
                        % (jp, fmt_num(v), fmt_num(mn), fmt_num(step), unit, round(k, 4)), ver)
                    return
            add("B-param", "parameter_domain", "PASS",
                "参数值落在区间域内",
                "%s=%s ∈ [%s, %s] step=%s %s" % (jp, fmt_num(v), fmt_num(mn), fmt_num(mx),
                                                 fmt_num(step), unit), ver)

    for i, plan in enumerate(plans):
        ver = plan.get("version", "v%d" % (i + 1))
        params = plan.get("parameters") if isinstance(plan.get("parameters"), dict) else {}
        for pname, pval in params.items():
            jp = "candidate_plans[%d].parameters.%s" % (i, pname)
            dom = pd.get(pname)
            if not isinstance(dom, dict):
                add("B-param", "parameter_domain", "WARN",
                    "候选使用了 parameter_domains 中未登记的参数",
                    "%s=%r：无对应有限参数域，需人工确认其合法性与依据" % (jp, pval), ver)
                continue
            values = pval if isinstance(pval, list) else [pval]
            for v in values:
                if is_num(v):
                    check_value_in_domain(pname, v, dom, jp, ver)
                else:
                    add("B-param", "parameter_domain", "WARN",
                        "参数值非数值，跳过域校验", "%s=%r" % (jp, v), ver)

    # (c) 候选引用的设备/试剂是否在合同（含文本内嵌补充）内
    id_pat = re.compile(r"\b(?:EQ|RE)-[A-Za-z0-9]+\b")
    for i, plan in enumerate(plans):
        ver = plan.get("version", "v%d" % (i + 1))
        for j, ci in enumerate(plan.get("cost_items") or []):
            if not isinstance(ci, dict) or "item" not in ci:
                continue
            jp = "candidate_plans[%d].cost_items[%d].item" % (i, j)
            m = match_known(ci.get("item"), known)
            if m:
                note = "（来源：文本内嵌补充）" if m.get("origin") == "text_embedded" else ""
                add("C-ref", "contract_coverage", "PASS",
                    "成本行引用的设备/试剂在合同内" + note,
                    "%s='%s' 匹配 %s（id=%s, origin=%s）"
                    % (jp, ci.get("item"), m.get("name"), m.get("id"), m.get("origin")), ver)
            else:
                add("C-ref", "contract_coverage", "FAIL",
                    "成本行引用的设备/试剂不在合同（含文本内嵌补充）内",
                    "%s='%s' 无法匹配任何已知设备/试剂 id 或名称" % (jp, ci.get("item")), ver)
        for tok in sorted(set(id_pat.findall(str(plan.get("summary", ""))))):
            m = match_known(tok, known)
            if m:
                add("C-ref", "contract_coverage", "PASS",
                    "summary 中引用的 id 在合同内",
                    "candidate_plans[%d].summary 中 '%s' 匹配 %s"
                    % (i, tok, m.get("name")), ver)
            else:
                add("C-ref", "contract_coverage", "FAIL",
                    "summary 中引用的 id 不在合同（含文本内嵌补充）内",
                    "candidate_plans[%d].summary 中 '%s' 无法匹配" % (i, tok), ver)

    # (d) budget_cap / deadline_days / 预约吞吐 vs 候选宣称
    for i, plan in enumerate(plans):
        ver = plan.get("version", "v%d" % (i + 1))
        total, est = plan.get("total_cost"), plan.get("est_days")
        if is_num(budget) and is_num(total):
            if total <= budget:
                add("D-budget", "budget_deadline", "PASS", "total_cost 未超预算上限",
                    "total_cost %s <= budget_cap %s %s（余量 %s）"
                    % (fmt_num(total), fmt_num(budget), cur, fmt_num(round(budget - total, 6))), ver)
            else:
                add("D-budget", "budget_deadline", "FAIL", "total_cost 超出预算上限",
                    "total_cost %s > budget_cap %s %s（超支 %s）"
                    % (fmt_num(total), fmt_num(budget), cur, fmt_num(round(total - budget, 6))), ver)
        if is_num(deadline) and is_num(est):
            if est <= deadline:
                add("D-deadline", "budget_deadline", "PASS", "est_days 未超周期上限",
                    "est_days %s <= deadline_days %s（余量 %s 天）"
                    % (fmt_num(est), fmt_num(deadline), fmt_num(deadline - est)), ver)
            else:
                add("D-deadline", "budget_deadline", "FAIL", "est_days 超出周期上限",
                    "est_days %s > deadline_days %s（超出 %s 天）"
                    % (fmt_num(est), fmt_num(deadline), fmt_num(est - deadline)), ver)
        # 预约吞吐：成本行匹配到设备的，所需机时 vs 预约窗口内可用机时
        for j, ci in enumerate(plan.get("cost_items") or []):
            if not isinstance(ci, dict):
                continue
            m = match_known(ci.get("item"), known)
            if not m or m.get("kind") != "equipment" or not isinstance(m.get("booking"), dict):
                continue
            bk = m["booking"]
            if not all(is_num(bk.get(k)) for k in ("window_days", "slots_per_week", "slot_hours")):
                continue
            weeks = bk["window_days"] / 7.0
            capacity = bk["slots_per_week"] * bk["slot_hours"] * weeks
            need = ci.get("quantity") if is_num(ci.get("quantity")) else None
            if need is None:
                continue
            if need <= capacity + 1e-9:
                add("D-booking", "budget_deadline", "PASS", "设备机时需求在预约吞吐能力内",
                    "%s 需 %s h；%s 窗口 %s 天可约 %s slot/周×%s h ≈ %.1f h"
                    % (ci.get("item"), fmt_num(need), m.get("name"), bk["window_days"],
                       bk["slots_per_week"], bk["slot_hours"], capacity), ver)
            else:
                add("D-booking", "budget_deadline", "FAIL", "设备机时需求超出预约吞吐能力",
                    "%s 需 %s h > %s 窗口 %s 天内可约 ≈ %.1f h（缺口 %.1f h）"
                    % (ci.get("item"), fmt_num(need), m.get("name"), bk["window_days"],
                       capacity, need - capacity), ver)
            if is_num(est) and est > bk["window_days"]:
                add("D-booking", "budget_deadline", "WARN", "est_days 超出设备预约窗口",
                    "est_days %s > %s booking.window_days %s，排期可行性存疑"
                    % (fmt_num(est), m.get("name"), bk["window_days"]), ver)

    # (e) 参数域 basis 与 source 定位
    for name, dom in pd.items():
        if not isinstance(dom, dict):
            continue
        basis, srcref = dom.get("basis"), dom.get("source")
        jp = "parameter_domains.%s" % name
        if not basis:
            add("E-basis", "domain_basis", "WARN", "参数域缺少 basis 标注", jp, None)
        if not srcref:
            add("E-basis", "domain_basis", "WARN", "参数域缺少 source 定位路径",
                "%s: basis=%r, source 缺失" % (jp, basis), None)
            continue
        ok, detail = resolve_case_path(case, srcref)
        if ok:
            add("E-basis", "domain_basis", "PASS", "参数域 source 可在 case 内定位",
                "%s: basis=%r, source=%s → %s" % (jp, basis, srcref, detail), None)
        else:
            add("E-basis", "domain_basis", "WARN", "参数域 source 无法在 case 内定位",
                "%s: basis=%r, source=%s → 解析失败（%s）；该依据需人工确认或补充材料"
                % (jp, basis, srcref, detail), None)
        if basis and "文献" in str(basis):
            src = case.get("source") if isinstance(case.get("source"), dict) else {}
            if not src.get("paper_pdf"):
                add("E-basis", "domain_basis", "WARN",
                    "basis 标注'文献'但 source.paper_pdf 缺失",
                    "%s: basis=%r" % (jp, basis), None)

    summary = {"PASS": 0, "FAIL": 0, "WARN": 0}
    for c in checks:
        summary[c["status"]] = summary.get(c["status"], 0) + 1
    report = {
        "case_id": case.get("case_id"),
        "generated_by": "scripts/case_reconcile.py reconcile",
        "check_count": len(checks),
        "summary": summary,
        "revision_targets": [c["check_id"] + "@" + str(c["candidate_version"])
                             for c in checks if c["status"] == "FAIL"],
        "checks": checks,
    }
    return report


def cmd_reconcile(args):
    case, err = load_json(args.case)
    out = args.out
    if err:
        write_json(out, {"case_id": None, "partial": True, "errors": [err],
                         "summary": {"PASS": 0, "FAIL": 0, "WARN": 0},
                         "revision_targets": [], "checks": []})
        print("[reconcile] partial: %s" % err)
        return 0
    report = reconcile(case)
    write_json(out, report)
    s = report["summary"]
    print("[reconcile] PASS=%d FAIL=%d WARN=%d -> %s" % (s["PASS"], s["FAIL"], s["WARN"], out))
    for c in report["checks"]:
        if c["status"] == "FAIL":
            print("  FAIL [%s] %s: %s" % (c["candidate_version"], c["description"],
                                          c["evidence"]))
    return 0


# ---------------------------------------------------------------- pdfscan

STOPWORDS = {
    "with", "from", "that", "this", "then", "than", "into", "over", "under",
    "the", "and", "for", "are", "not", "within", "target",
}


def goal_keywords(goal):
    kws = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]{2,}", goal or ""):
        lw = w.lower()
        if lw not in STOPWORDS:
            kws.add(w)
    for run in re.findall(r"[一-鿿]{2,}", goal or ""):
        kws.add(run)
        if len(run) > 4:  # 长中文串再切 2-4 gram，避免整句匹配不到
            for n in (4, 3, 2):
                for i in range(0, len(run) - n + 1):
                    kws.add(run[i:i + n])
    return sorted(kws)


def cmd_pdfscan(args):
    inputdir = args.inputdir
    goal = args.goal
    case = {}
    if args.case:
        case, _ = load_json(args.case)
        if not goal:
            goal = case.get("research_goal", "")
    lines = ["# PDF 摘录（pdfscan）", ""]
    pdfs = []
    if os.path.isdir(inputdir):
        pdfs = sorted(f for f in os.listdir(inputdir) if f.lower().endswith(".pdf"))
    if not pdfs:
        lines.append("**未在 %s 下发现 PDF 文件。**本案例无可扫描的论文材料；"
                     "若 case.json 的 source.paper_pdf 指向某文件，请确认其是否已挂载到输入目录。"
                     % inputdir)
        write_text(args.out, "\n".join(lines) + "\n")
        print("[pdfscan] no PDF found under %s -> %s" % (inputdir, args.out))
        return 0
    pdftotext = shutil.which("pdftotext") or os.environ.get("PDFTOTEXT")
    if not pdftotext:
        lines.append("**pdftotext 不可用**（PATH 中未找到，且未设置 PDFTOTEXT 环境变量）。"
                     "发现 PDF：%s，但无法机械提取文本；请人工阅读，不得凭记忆引用页码。"
                     % ", ".join(pdfs))
        write_text(args.out, "\n".join(lines) + "\n")
        print("[pdfscan] pdftotext unavailable; reported honestly -> %s" % args.out)
        return 0
    kws = goal_keywords(goal)
    lines.append("- pdftotext: %s" % pdftotext)
    lines.append("- research_goal 关键词: %s" % ", ".join(kws[:40]))
    lines.append("")
    for pdf in pdfs:
        path = os.path.join(inputdir, pdf)
        lines.append("## %s" % pdf)
        lines.append("")
        try:
            proc = subprocess.run([pdftotext, "-layout", path, "-"],
                                  capture_output=True, text=True, timeout=60)
        except Exception as e:  # noqa: BLE001
            lines.append("提取失败：%s: %s" % (type(e).__name__, e))
            continue
        if proc.returncode != 0:
            lines.append("pdftotext 返回非零（%d）：%s" % (proc.returncode,
                                                         proc.stderr.strip()[:300]))
            continue
        pages = proc.stdout.split("\f")
        hit_pages = 0
        for pno, page in enumerate(pages, start=1):
            if not page.strip():
                continue
            page_lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
            hits = []
            for idx, ln in enumerate(page_lines):
                low = ln.lower()
                if any(k.lower() in low for k in kws):
                    ctx = page_lines[max(0, idx - 1): idx + 2]
                    hits.append(" / ".join(ctx))
            if hits:
                hit_pages += 1
                lines.append("### 第 %d 页" % pno)
                for h in hits[:4]:
                    lines.append("> %s" % h[:400])
                lines.append("")
        if hit_pages == 0:
            lines.append("未检索到与 research_goal 关键词相关的段落（如实报告，不捏造页码）。")
            lines.append("")
    write_text(args.out, "\n".join(lines) + "\n")
    print("[pdfscan] scanned %d pdf(s) -> %s" % (len(pdfs), args.out))
    return 0


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(
        description="exp-source-reconciler: case.json 事实登记与三方机械对账")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("extract", help="解析 case.json → facts.json + facts.md")
    p.add_argument("--case", required=True, help="case.json 路径")
    p.add_argument("--outdir", required=True, help="输出目录")
    p.set_defaults(func=cmd_extract)

    p = sub.add_parser("reconcile", help="对账检查 → reconcile_report.json")
    p.add_argument("--case", required=True, help="case.json 路径")
    p.add_argument("--facts", default=None, help="可选：extract 生成的 facts.json（仅留档用）")
    p.add_argument("--out", required=True, help="reconcile_report.json 输出路径")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("pdfscan", help="扫描输入目录 PDF → pdf_excerpts.md")
    p.add_argument("--inputdir", required=True, help="输入目录（如 /input）")
    p.add_argument("--case", default=None, help="可选：case.json，用于取 research_goal")
    p.add_argument("--goal", default=None, help="可选：直接给出检索目标文本")
    p.add_argument("--out", required=True, help="pdf_excerpts.md 输出路径")
    p.set_defaults(func=cmd_pdfscan)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
