#!/usr/bin/env python3
"""fp_screen.py — 误报鉴别筛（把学科惯例/风格差异误判为违规的 finding 拦下）。

对每条 finding 按其 type 跑机器可读鉴别规则表（references/discrimination_rules.md
的子集，内嵌于本脚本，保持纯 stdlib、确定性）。每条输出：
  fp_decision ∈ {keep, downgrade, drop}
  fp_rule      触发的规则名（FP-xx，与 discrimination_rules.md 编号一致）
  fp_reason    一句理由

drop 的 finding 不删除，而是 fp_decision=drop 且 verdict_status=误报排除，
便于审计复跑；下游（adjudicate.py）只对 keep 的条目生成对抗复核卡。

用法：
  python3 fp_screen.py --input gated.json --output screened.json --log fp_log.json

输入可以是 severity_gate.py 的输出（{"findings": [...]}）或裸 findings 列表。
缺键不崩，exit 0。
"""
import argparse
import json
import sys

# ---------------------------------------------------------------------------
# 鉴别规则表（references/discrimination_rules.md 的机器可读子集）
# 每条规则：(规则名, 适用的 type 集合(None=全部), 判定函数(finding, flags) ->
#            (decision, reason) 或 None 表示不适用)
# decision ∈ {"keep", "downgrade", "drop"}
# 规则按顺序评估，第一条命中的非 keep 结果即生效；否则 keep。
# ---------------------------------------------------------------------------

FP_TYPES_REFERENCE = {
    "reference_error",
    "reference_style",
    "citation_format",
    "metadata_mismatch",
    "missing_doi",
    "fabrication_suspected",
    "integrity",
}


def _flags(finding):
    fl = finding.get("context_flags")
    return fl if isinstance(fl, dict) else {}


def _type(finding):
    return str(finding.get("type") or "")


def rule_fp01_no_doi(finding, flags):
    """FP-01 无 DOI：人文/会议/报告/预印本惯例可无 DOI，不报。"""
    if _type(finding) not in FP_TYPES_REFERENCE:
        return None
    if flags.get("no_doi") and flags.get("reference_type") in (
        "conference",
        "humanities_book",
        "report",
        "preprint",
        "thesis",
        "standard",
    ):
        return (
            "drop",
            "无 DOI 属于 %s 类文献的学科惯例（discrimination_rules.md FP-01），不构成问题"
            % flags.get("reference_type"),
        )
    return None


def rule_fp02_mixed_style(finding, flags):
    """FP-02 体例混用：仅当同一文献表内两种体例并存才报。"""
    if _type(finding) not in {"reference_style", "citation_format"}:
        return None
    if not flags.get("mixed_styles_in_same_list"):
        return (
            "drop",
            "未确认同一参考文献表内两种体例并存，全刊统一体例差异属风格问题（FP-02）",
        )
    return None


def rule_fp03_name_variant(finding, flags):
    """FP-03 作者名拼写变体：仅拼写/缩写差异不单判 metadata_mismatch。"""
    if _type(finding) not in {"metadata_mismatch", "reference_error"}:
        return None
    if flags.get("name_variants_only"):
        return (
            "drop",
            "仅作者名拼写/缩写变体（如 van der Berg vs van der Berg, J.），"
            "著录差异非元数据错误（FP-03）",
        )
    return None


def rule_fp04_preprint(finding, flags):
    """FP-04 预印本/会议/报告：合法存在形式不判 fabricated。"""
    if _type(finding) not in {"fabrication_suspected", "integrity", "reference_error"}:
        return None
    if flags.get("is_preprint") or flags.get("reference_type") in (
        "preprint",
        "conference",
        "report",
    ):
        if not flags.get("external_record"):
            return (
                "drop",
                "预印本/会议/报告是合法存在形式，无外部记录时不判疑似捏造（FP-04）",
            )
    return None


def rule_fp05_ethics_suggestion(finding, flags):
    """FP-05 缺伦理声明：norm_issue（规范缺失），不得判 misconduct/integrity。"""
    if _type(finding) in {"integrity", "misconduct", "ethics_misconduct"} and flags.get(
        "missing_ethics_statement"
    ):
        return (
            "downgrade",
            "缺少伦理声明是 norm_issue（规范缺失），非学术不端；改判 norm_issue（FP-05）",
        )
    return None


def rule_fp06_self_citation(finding, flags):
    """FP-06 自我引用：与主题相关且比例不过高不报。"""
    if _type(finding) not in {"self_citation", "citation_abuse"}:
        return None
    if not flags.get("self_citation_excessive"):
        return (
            "drop",
            "自我引用与主题相关且未达异常比例，属正常学术行为（FP-06）",
        )
    return None


def rule_fp07_p_value_style(finding, flags):
    """FP-07 p 值写法习惯：仅写法差异（P<0.05 vs p=.032）不报。"""
    if _type(finding) not in {"statistics_error", "p_value_error"}:
        return None
    if flags.get("p_value_style_only"):
        return (
            "drop",
            "仅 p 值报告写法差异，数值可复算一致，属统计报告习惯（FP-07）",
        )
    return None


def rule_fp08_suggestion_only(finding, flags):
    """FP-08 纯建议条目不得携带规范问题严重度。"""
    if _type(finding) in {"suggestion", "writing_suggestion"} or flags.get(
        "suggestion_only"
    ):
        sev = str(finding.get("severity") or "info")
        if sev in ("critical", "major"):
            return (
                "downgrade",
                "建议性意见不构成规范问题，降为 suggestion/info（FP-08）",
            )
    return None


def rule_fp09_figure_caption(finding, flags):
    """FP-09 图注详略：信息要素齐全时详略差异不报。"""
    if _type(finding) not in {"figure_issue", "caption_issue"}:
        return None
    if flags.get("caption_complete"):
        return (
            "drop",
            "图注要素（样本量、统计方法、显著性标记）齐全，详略属风格（FP-09）",
        )
    return None


def rule_fp10_abstract_diff(finding, flags):
    """FP-10 中英文摘要差异：详略不同不报，结论矛盾才报。"""
    if _type(finding) not in {"abstract_inconsistency", "translation_issue"}:
        return None
    if not flags.get("conclusions_conflict"):
        return (
            "drop",
            "中英文摘要仅详略差异、结论一致，属惯例（FP-10）",
        )
    return None


RULES = [
    ("FP-01_no_doi_convention", rule_fp01_no_doi),
    ("FP-02_mixed_style_same_list", rule_fp02_mixed_style),
    ("FP-03_author_name_variant", rule_fp03_name_variant),
    ("FP-04_preprint_legitimate", rule_fp04_preprint),
    ("FP-05_ethics_norm_not_misconduct", rule_fp05_ethics_suggestion),
    ("FP-06_self_citation_normal", rule_fp06_self_citation),
    ("FP-07_p_value_style", rule_fp07_p_value_style),
    ("FP-08_suggestion_not_violation", rule_fp08_suggestion_only),
    ("FP-09_caption_detail_style", rule_fp09_figure_caption),
    ("FP-10_abstract_detail_diff", rule_fp10_abstract_diff),
]


def screen_finding(finding, index):
    if not isinstance(finding, dict):
        finding = {}
    f = dict(finding)
    fid = f.get("id") or "finding-%03d" % (index + 1)
    f["id"] = fid
    flags = _flags(f)

    decision, rule_name, reason = "keep", "FP-00_no_rule_hit", "无鉴别规则命中，维持"
    for name, func in RULES:
        try:
            hit = func(f, flags)
        except Exception:
            hit = None
        if hit:
            decision, reason = hit
            rule_name = name
            break

    f["fp_decision"] = decision
    f["fp_rule"] = rule_name
    f["fp_reason"] = reason
    if decision == "drop":
        f["verdict_status"] = "误报排除"
    elif decision == "downgrade":
        if _type(f) in {"integrity", "misconduct", "ethics_misconduct"}:
            f["type"] = "norm_issue"
        f["category"] = (
            "suggestion"
            if rule_name == "FP-08_suggestion_not_violation"
            else f.get("category", "norm_issue")
        )
        order = ["info", "minor", "major", "critical"]
        sev = str(f.get("severity") or "minor")
        if sev in order and order.index(sev) > 1:
            f["severity"] = order[order.index(sev) - 1]
        elif rule_name == "FP-08_suggestion_not_violation":
            f["severity"] = "info"
    return f


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="误报鉴别筛：按 FP-01…FP-10 规则表对 findings 输出 keep/downgrade/drop。"
    )
    parser.add_argument("--input", required=True, help="findings JSON（severity_gate 输出或裸列表）")
    parser.add_argument("--output", required=True, help="鉴别后 findings JSON 输出路径")
    parser.add_argument("--log", default=None, help="鉴别日志路径（默认 <output>.fp_log.json）")
    args = parser.parse_args(argv)

    result = {
        "note": "fp_screen 输出：误报鉴别后的 findings（drop 条目不删除，标注误报排除）",
        "findings": [],
        "fp_log": [],
        "fp_errors": [],
        "summary": {},
    }

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        result["fp_errors"].append("读取输入失败: %s" % exc)
        data = {}

    findings = []
    if isinstance(data, dict):
        findings = data.get("findings") or []
    elif isinstance(data, list):
        findings = data
    if not isinstance(findings, list):
        result["fp_errors"].append("findings 字段不是列表，按空处理")
        findings = []

    out = []
    log_entries = []
    n_keep = n_down = n_drop = 0
    for i, finding in enumerate(findings):
        try:
            sf = screen_finding(finding, i)
        except Exception as exc:
            sf = finding if isinstance(finding, dict) else {}
            sf.setdefault("id", "finding-%03d" % (i + 1))
            sf.update(
                fp_decision="keep",
                fp_rule="ERROR",
                fp_reason="处理异常，原样保留: %s" % exc,
            )
        out.append(sf)
        log_entries.append(
            {
                "finding_id": sf["id"],
                "fp_decision": sf["fp_decision"],
                "fp_rule": sf["fp_rule"],
                "fp_reason": sf["fp_reason"],
            }
        )
        if sf["fp_decision"] == "keep":
            n_keep += 1
        elif sf["fp_decision"] == "downgrade":
            n_down += 1
        else:
            n_drop += 1

    result["findings"] = out
    result["fp_log"] = log_entries
    result["summary"] = {
        "total": len(out),
        "keep": n_keep,
        "downgrade": n_down,
        "drop": n_drop,
    }

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("写入输出失败: %s" % exc, file=sys.stderr)

    log_path = args.log or (args.output + ".fp_log.json")
    try:
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(
                {"note": "fp_screen 鉴别日志", "fp_log": log_entries, "summary": result["summary"]},
                fh,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as exc:
        print("写入日志失败: %s" % exc, file=sys.stderr)

    print(
        "fp_screen: %d 条 finding → keep %d / downgrade %d / drop %d"
        % (len(out), n_keep, n_down, n_drop)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
