#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
risk_fmea.py — exp-risk-fmea skill 核心脚本：失效模式驱动设计 (FMEA)。

仅依赖 Python 3 标准库；输出确定性（无随机、无墙钟时间）；
输入缺键/缺文件时不崩溃：输出 status=partial 的报告并 exit 0。

子命令：
  map            方案步骤表 -> 失效模式映射，输出 risk_map.json
  audit          风险完备性审查（覆盖率 + 缺口清单），输出 audit_report.json
  decision_tree  高 RPN 失效模式 -> 异常处置决策树，输出 anomaly_tree.md
  render         risk_map.json -> 方案"风险与异常处置"章节 markdown（机械生成，禁止手写替代）

失效模式库来源：references/failure_mode_library.md 中第一个 ```json 代码块（可扩展）。
评分：severity / occurrence / detection 各 1-5，RPN = 三者乘积（最大 125）。
高优先级规则：RPN >= 阈值（默认 24）或 severity >= 5（安全类无论 RPN 一律升级）。
"""
import argparse
import json
import os
import re
import sys

DEFAULT_RPN_THRESHOLD = 24
SEVERITY_FORCE_LEVEL = 5  # severity >= 5 的失效模式无论 RPN 一律进入决策树
REQUIRED_FM_ELEMENTS = ["detection_criterion", "stop_loss", "fallback"]
REQUIRED_CONFIRM_CATEGORIES = ["安全", "伦理", "设备可用性", "专家确认"]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LIBRARY = os.path.join(SCRIPT_DIR, "..", "references", "failure_mode_library.md")


# ---------------------------------------------------------------- 工具函数

def clamp_score(v, lo=1, hi=5):
    try:
        v = int(v)
    except Exception:
        return lo
    return max(lo, min(hi, v))


def load_json(path, default=None):
    if default is None:
        default = {}
    if not path:
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_library(path):
    """从 markdown 参考文件中抽取第一个 ```json 代码块作为失效模式库。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return None, "library unreadable: %s (%s)" % (path, e)
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if not m:
        return None, "no ```json block found in library file: %s" % path
    try:
        lib = json.loads(m.group(1))
    except Exception as e:
        return None, "library json parse error: %s" % e
    if not isinstance(lib.get("failure_modes"), list) or not isinstance(lib.get("prototypes"), list):
        return None, "library json must contain 'prototypes' and 'failure_modes' lists"
    return lib, None


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def safe_out(report, out_path):
    """报告落盘；无 out 路径时打到 stdout。永不抛异常。"""
    try:
        if out_path:
            if isinstance(report, str):
                write_text(out_path, report)
            else:
                write_json(out_path, report)
        else:
            if isinstance(report, str):
                sys.stdout.write(report)
            else:
                sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except Exception as e:
        sys.stdout.write(json.dumps({"status": "partial", "error": "write failed: %s" % e},
                                    ensure_ascii=False) + "\n")
    return 0


# ---------------------------------------------------------------- map

def kw_match(kw, text):
    """纯 ASCII 关键词按词边界匹配（避免 tem 误中 temperature）；
    含 CJK 的关键词按子串匹配。"""
    kw = str(kw).lower()
    if not kw:
        return False
    if all(ord(c) < 128 for c in kw):
        return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None
    return kw in text


def match_prototypes(step, prototypes):
    text = " ".join(str(x) for x in [
        step.get("name", ""),
        step.get("description", ""),
        " ".join(str(t) for t in (step.get("tags") or [])),
    ]).lower()
    hints = step.get("prototype_hint") or []
    if isinstance(hints, str):
        hints = [hints]
    matched = []
    for p in prototypes:
        if p.get("id") in hints:
            matched.append(p)
            continue
        for kw in p.get("keywords", []):
            if kw_match(kw, text):
                matched.append(p)
                break
    return matched


def build_fm_entry(step, proto, fm_base, threshold):
    ov = (step.get("overrides") or {}).get(fm_base.get("id"), {}) or {}
    s = clamp_score(ov.get("severity", fm_base.get("severity", 1)))
    o = clamp_score(ov.get("occurrence", fm_base.get("occurrence", 1)))
    d = clamp_score(ov.get("detection", fm_base.get("detection", 1)))
    rpn = s * o * d
    return {
        "failure_mode_id": fm_base.get("id", ""),
        "name": fm_base.get("name", ""),
        "category": fm_base.get("category", ""),
        "prototype": proto.get("name", ""),
        "detection_criterion": fm_base.get("detection_criterion", ""),
        "confirm_method": fm_base.get("confirm_method", ""),
        "stop_loss": fm_base.get("stop_loss", ""),
        "fallback": fm_base.get("fallback", ""),
        "owner": fm_base.get("owner", ""),
        "escalation": fm_base.get("escalation", ""),
        "design_feedback": fm_base.get("design_feedback", ""),
        "severity": s, "occurrence": o, "detection": d, "rpn": rpn,
        "score_notes": ov.get("reason", ""),
        "high_priority": bool(rpn >= threshold or s >= SEVERITY_FORCE_LEVEL),
    }


def cmd_map(args):
    lib, err = load_library(args.library)
    steps_doc = load_json(args.steps, {})
    case = load_json(args.case, {})
    if lib is None:
        return safe_out({"status": "partial", "note": args.note, "error": err,
                         "steps": [], "summary": {}}, args.out)
    steps = steps_doc.get("steps") or []
    if not isinstance(steps, list) or not steps:
        return safe_out({"status": "partial", "note": args.note,
                         "error": "steps file missing/unreadable or contains no steps: %s"
                                  % args.steps,
                         "steps": [], "summary": {}}, args.out)
    fm_by_id = {fm.get("id"): fm for fm in lib.get("failure_modes", [])}
    prototypes = lib.get("prototypes", [])

    out_steps, warnings = [], []
    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            step = {"name": str(step)}
        sid = step.get("id") or "ST-%02d" % (idx + 1)
        matched = match_prototypes(step, prototypes)
        fms, seen = [], set()
        for p in matched:
            for fid in p.get("failure_modes", []):
                if fid in seen or fid not in fm_by_id:
                    continue
                seen.add(fid)
                fms.append(build_fm_entry(step, p, fm_by_id[fid], args.threshold))
        fms.sort(key=lambda e: (-e["rpn"], e["failure_mode_id"]))
        flags = []
        if not fms:
            flags.append("ORPHAN-WARN")
            warnings.append({"step_id": sid, "warn": "ORPHAN-WARN",
                             "detail": "步骤未被任何失效模式覆盖：请补充步骤关键词到 "
                                       "references/failure_mode_library.md 词表，"
                                       "或在步骤上加 prototype_hint"})
        out_steps.append({
            "id": sid,
            "name": step.get("name", ""),
            "description": step.get("description", ""),
            "matched_prototypes": [p.get("name", "") for p in matched],
            "flags": flags,
            "failure_modes": fms,
        })

    all_fms = [(st["id"], fm) for st in out_steps for fm in st["failure_modes"]]
    high = [(sid, fm) for sid, fm in all_fms if fm["high_priority"]]
    high.sort(key=lambda t: (-t[1]["rpn"], t[0], t[1]["failure_mode_id"]))
    max_entry = None
    if all_fms:
        sid, fm = max(all_fms, key=lambda t: (t[1]["rpn"], t[1]["failure_mode_id"]))
        max_entry = {"step_id": sid, "failure_mode_id": fm["failure_mode_id"],
                     "name": fm["name"], "rpn": fm["rpn"],
                     "severity": fm["severity"], "occurrence": fm["occurrence"],
                     "detection": fm["detection"]}
    report = {
        "status": "complete",
        "note": args.note,
        "generated_by": "risk_fmea.py map",
        "case_id": case.get("case_id", ""),
        "rpn_threshold": args.threshold,
        "high_priority_rule": "rpn >= threshold OR severity >= %d" % SEVERITY_FORCE_LEVEL,
        "resource_context": {
            "budget_cap": (case.get("resource_contract") or {}).get("budget_cap"),
            "deadline_days": (case.get("resource_contract") or {}).get("deadline_days"),
            "equipment_ids": [e.get("id") for e in
                              (case.get("resource_contract") or {}).get("equipment", [])
                              if isinstance(e, dict)],
            "reagent_ids": [r.get("id") for r in
                            (case.get("resource_contract") or {}).get("reagents", [])
                            if isinstance(r, dict)],
            "contract_disclaimer": (case.get("resource_contract") or {}).get("disclaimer", ""),
        },
        "steps": out_steps,
        "warnings": warnings,
        "summary": {
            "total_steps": len(out_steps),
            "mapped_steps": sum(1 for s in out_steps if s["failure_modes"]),
            "orphan_steps": [s["id"] for s in out_steps if not s["failure_modes"]],
            "total_failure_modes": len(all_fms),
            "high_priority_count": len(high),
            "max_rpn": max_entry,
        },
    }
    return safe_out(report, args.out)


# ---------------------------------------------------------------- audit

def cmd_audit(args):
    rm = load_json(args.risk_map, {})
    conf_doc = load_json(args.confirmations, {}) if args.confirmations else {}
    plan = load_json(args.plan, {}) if args.plan else {}
    if not rm.get("steps"):
        return safe_out({"status": "partial", "note": args.note,
                         "error": "risk_map missing or has no steps: %s" % args.risk_map,
                         "coverage": {}, "gaps": []}, args.out)
    items = conf_doc.get("confirmation_items") or plan.get("confirmation_items") or []

    gaps = []
    steps = rm.get("steps", [])
    total_steps = len(steps)
    covered_steps = 0
    total_fm = 0
    complete_fm = 0
    for st in steps:
        fms = st.get("failure_modes", [])
        if fms:
            covered_steps += 1
        else:
            gaps.append({"type": "ORPHAN-STEP", "step_id": st.get("id"),
                         "detail": "步骤未被任何失效模式覆盖（ORPHAN-WARN 未消解）"})
        for fm in fms:
            total_fm += 1
            missing = [k for k in REQUIRED_FM_ELEMENTS
                       if not str(fm.get(k, "")).strip()]
            if not str(fm.get("owner", "")).strip() and not fm.get("confirmation_ref"):
                missing.append("owner_or_confirmation")
            if missing:
                gaps.append({"type": "FM-ELEMENT-MISSING",
                             "step_id": st.get("id"),
                             "failure_mode_id": fm.get("failure_mode_id"),
                             "missing_elements": missing})
            else:
                complete_fm += 1

    present_cats = set()
    for it in items:
        if not isinstance(it, dict):
            continue
        cat = str(it.get("category", ""))
        for req in REQUIRED_CONFIRM_CATEGORIES:
            if req in cat:
                present_cats.add(req)
    missing_cats = [c for c in REQUIRED_CONFIRM_CATEGORIES if c not in present_cats]
    for c in missing_cats:
        gaps.append({"type": "CONFIRM-CATEGORY-MISSING", "category": c,
                     "detail": "confirmation_items 缺少「%s」类确认项" % c})

    step_cov = covered_steps / total_steps if total_steps else 0.0
    fm_cov = complete_fm / total_fm if total_fm else 0.0
    conf_cov = (len(REQUIRED_CONFIRM_CATEGORIES) - len(missing_cats)) / \
        float(len(REQUIRED_CONFIRM_CATEGORIES))
    passed = (step_cov == 1.0 and fm_cov == 1.0 and not missing_cats)
    report = {
        "status": "complete",
        "note": args.note,
        "generated_by": "risk_fmea.py audit",
        "verdict": "PASS" if passed else "GAP",
        "coverage": {
            "step_coverage": round(step_cov, 4),
            "covered_steps": covered_steps,
            "total_steps": total_steps,
            "fm_element_completeness": round(fm_cov, 4),
            "complete_failure_modes": complete_fm,
            "total_failure_modes": total_fm,
            "confirmation_category_coverage": round(conf_cov, 4),
            "confirmation_categories_present": sorted(present_cats),
            "confirmation_categories_missing": missing_cats,
            "overall_complete": passed,
        },
        "gaps": gaps,
        "iteration_hint": "" if passed else
        "按 gaps 修复后重跑 map/audit；每轮迭代必须先消解 ORPHAN-STEP，"
        "再补四要素，再补 confirmation_items 类别；最多迭代 3 轮，"
        "仍不达标则在 result.json 标注 honest partial。",
    }
    return safe_out(report, args.out)


# ---------------------------------------------------------------- decision_tree

def cmd_decision_tree(args):
    rm = load_json(args.risk_map, {})
    if not rm.get("steps"):
        return safe_out({"status": "partial", "note": args.note,
                         "error": "risk_map missing or empty: %s" % args.risk_map},
                        args.out)
    threshold = args.threshold if args.threshold is not None else \
        rm.get("rpn_threshold", DEFAULT_RPN_THRESHOLD)
    # 按失效模式聚合其出现的步骤
    grouped = {}
    for st in rm.get("steps", []):
        for fm in st.get("failure_modes", []):
            if fm.get("rpn", 0) >= threshold or fm.get("severity", 0) >= SEVERITY_FORCE_LEVEL:
                g = grouped.setdefault(fm["failure_mode_id"], {"fm": fm, "steps": []})
                g["steps"].append(st.get("id", ""))
                if fm.get("rpn", 0) > g["fm"].get("rpn", 0):
                    g["fm"] = fm
    ordered = sorted(grouped.values(),
                     key=lambda g: (-g["fm"].get("rpn", 0), g["fm"].get("failure_mode_id", "")))

    lines = []
    if args.note:
        lines.append("> %s" % args.note)
        lines.append("")
    lines.append("# 异常处置决策树（anomaly_tree.md）")
    lines.append("")
    lines.append("由 `risk_fmea.py decision_tree` 机械生成；"
                 "入选规则：RPN ≥ %d 或 severity ≥ %d（安全类无论 RPN 一律入选）。"
                 % (threshold, SEVERITY_FORCE_LEVEL))
    lines.append("")
    lines.append("## 通用处置流程（每个异常都按此顺序走）")
    lines.append("")
    lines.append("```")
    lines.append("异常信号出现")
    lines.append("  → 1. 判据确认：对照 detection_criterion 核实，用 confirm_method 排除误报")
    lines.append("  → 2. 止损动作：先执行 stop_loss（先于原因分析），保护样品/人员/设备")
    lines.append("  → 3. 替代路径：执行 fallback，方案不中断")
    lines.append("  → 4. 升级判断：满足 escalation 条件时停止自主处置，")
    lines.append("       升级人工/专家确认，并把确认结论写入 confirmation_items 与 change_log")
    lines.append("```")
    lines.append("")
    lines.append("## 高优先级失效模式决策树（共 %d 项）" % len(ordered))
    lines.append("")
    if not ordered:
        lines.append("（无失效模式达到入选阈值；仍建议保留通用处置流程。）")
        lines.append("")
    for i, g in enumerate(ordered, 1):
        fm = g["fm"]
        lines.append("### %d. %s %s — RPN %d（S%d×O%d×D%d）— 关联步骤：%s"
                     % (i, fm.get("failure_mode_id", ""), fm.get("name", ""),
                        fm.get("rpn", 0), fm.get("severity", 0),
                        fm.get("occurrence", 0), fm.get("detection", 0),
                        ", ".join(g["steps"])))
        if fm.get("score_notes"):
            lines.append("")
            lines.append("- 评分依据：%s" % fm["score_notes"])
        lines.append("")
        lines.append("- **异常触发判据**：%s" % fm.get("detection_criterion", ""))
        lines.append("- **判据确认方法**：%s" % fm.get("confirm_method", ""))
        lines.append("- **止损动作（立即执行）**：%s" % fm.get("stop_loss", ""))
        lines.append("- **替代路径**：%s" % fm.get("fallback", ""))
        lines.append("- **设计预防（已反向写入方案）**：%s" % fm.get("design_feedback", ""))
        lines.append("- **责任人**：%s" % fm.get("owner", ""))
        lines.append("- **何时升级人工/专家确认**：%s" % fm.get("escalation", ""))
        lines.append("")
    return safe_out("\n".join(lines), args.out)


# ---------------------------------------------------------------- render

def cmd_render(args):
    rm = load_json(args.risk_map, {})
    if not rm.get("steps"):
        return safe_out({"status": "partial", "note": args.note,
                         "error": "risk_map missing or empty: %s" % args.risk_map},
                        args.out)
    s = rm.get("summary", {})
    lines = []
    if args.note:
        lines.append("> %s" % args.note)
        lines.append("")
    lines.append("## 风险与异常处置（本章由 risk_map.json 机械生成，禁止手写替代或删改）")
    lines.append("")
    lines.append("- 步骤数：%s；被失效模式覆盖：%s；孤儿步骤：%s"
                 % (s.get("total_steps", 0), s.get("mapped_steps", 0),
                    ", ".join(s.get("orphan_steps", [])) or "无"))
    lines.append("- 失效模式条目：%s；高优先级：%s（规则：%s）"
                 % (s.get("total_failure_modes", 0), s.get("high_priority_count", 0),
                    rm.get("high_priority_rule", "")))
    mx = s.get("max_rpn") or {}
    if mx:
        lines.append("- 最高 RPN 项：%s %s @ %s，RPN=%s（S%s×O%s×D%s）"
                     % (mx.get("failure_mode_id"), mx.get("name"), mx.get("step_id"),
                        mx.get("rpn"), mx.get("severity"),
                        mx.get("occurrence"), mx.get("detection")))
    lines.append("")
    lines.append("### 高优先级失效模式 → 设计修改要求（预防优于处置）")
    lines.append("")
    any_high = False
    seen_hf = set()
    for st in rm.get("steps", []):
        for fm in st.get("failure_modes", []):
            if fm.get("high_priority"):
                key = (st["id"], fm["failure_mode_id"])
                if key in seen_hf:
                    continue
                seen_hf.add(key)
                any_high = True
                lines.append("- **[%s] %s %s（RPN %d）** → 设计要求：%s"
                             % (st["id"], fm["failure_mode_id"], fm["name"],
                                fm["rpn"], fm.get("design_feedback", "")))
    if not any_high:
        lines.append("- （无高优先级失效模式）")
    lines.append("")
    lines.append("### 逐步骤失效模式明细表")
    lines.append("")
    lines.append("| 步骤 | 失效模式 | S | O | D | RPN | 可观测判据 | 止损点 | 替代路径 | 责任人 |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for st in rm.get("steps", []):
        if not st.get("failure_modes"):
            lines.append("| %s %s | **ORPHAN-WARN：未覆盖** | - | - | - | - | - | - | - | - |"
                         % (st["id"], st.get("name", "")))
        for fm in st.get("failure_modes", []):
            lines.append("| %s %s | %s %s%s | %d | %d | %d | %d | %s | %s | %s | %s |"
                         % (st["id"], st.get("name", ""),
                            fm["failure_mode_id"], fm["name"],
                            " ⚠" if fm.get("high_priority") else "",
                            fm["severity"], fm["occurrence"], fm["detection"], fm["rpn"],
                            fm.get("detection_criterion", "").replace("|", "｜"),
                            fm.get("stop_loss", "").replace("|", "｜"),
                            fm.get("fallback", "").replace("|", "｜"),
                            fm.get("owner", "")))
    lines.append("")
    lines.append("详细异常处置流程见 anomaly_tree.md（decision_tree 子命令生成）。")
    lines.append("")
    return safe_out("\n".join(lines), args.out)


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="risk_fmea.py",
        description="exp-risk-fmea：失效模式驱动设计工具（map/audit/decision_tree/render）")
    sub = p.add_subparsers(dest="command")

    def common(sp):
        sp.add_argument("--note", default="",
                        help="写入输出文件头部的说明（示例运行传：合成示例输出，非正式测评结果）")

    sp = sub.add_parser("map", help="步骤表 -> risk_map.json（失效模式映射与 RPN 排序）")
    sp.add_argument("--case", required=True, help="case.json 路径（缺文件时输出 partial）")
    sp.add_argument("--steps", required=True, help="plan_steps.json 路径")
    sp.add_argument("--library", default=DEFAULT_LIBRARY,
                    help="failure_mode_library.md 路径（默认取 skill 内 references/）")
    sp.add_argument("--threshold", type=int, default=DEFAULT_RPN_THRESHOLD,
                    help="高优先级 RPN 阈值，默认 %d" % DEFAULT_RPN_THRESHOLD)
    sp.add_argument("--out", required=True, help="输出 risk_map.json 路径")
    common(sp)
    sp.set_defaults(func=cmd_map)

    sp = sub.add_parser("audit", help="风险完备性审查 -> audit_report.json")
    sp.add_argument("--risk-map", required=True, help="risk_map.json 路径")
    sp.add_argument("--confirmations", default="",
                    help="含 confirmation_items 的 JSON 路径（可选）")
    sp.add_argument("--plan", default="",
                    help="plan.json 路径（--confirmations 缺省时从其取 confirmation_items）")
    sp.add_argument("--out", required=True, help="输出 audit_report.json 路径")
    common(sp)
    sp.set_defaults(func=cmd_audit)

    sp = sub.add_parser("decision_tree", help="高 RPN 失效模式 -> anomaly_tree.md")
    sp.add_argument("--risk-map", required=True, help="risk_map.json 路径")
    sp.add_argument("--threshold", type=int, default=None,
                    help="RPN 阈值，缺省沿用 risk_map 中的阈值")
    sp.add_argument("--out", required=True, help="输出 anomaly_tree.md 路径")
    common(sp)
    sp.set_defaults(func=cmd_decision_tree)

    sp = sub.add_parser("render", help="risk_map.json -> 方案风险章节 markdown")
    sp.add_argument("--risk-map", required=True, help="risk_map.json 路径")
    sp.add_argument("--out", required=True, help="输出 risk_section.md 路径")
    common(sp)
    sp.set_defaults(func=cmd_render)

    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not getattr(args, "func", None):
        build_parser().print_help()
        return 0
    try:
        return args.func(args)
    except Exception as e:  # 缺键/异常输入一律不崩：partial + exit 0
        out = getattr(args, "out", "")
        return safe_out({"status": "partial",
                         "note": getattr(args, "note", ""),
                         "error": "%s: %s" % (type(e).__name__, e)}, out)


if __name__ == "__main__":
    sys.exit(main())
