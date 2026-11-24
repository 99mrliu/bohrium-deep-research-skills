#!/usr/bin/env python3
"""adjudicate.py — 对抗式复核（控辩二审）与终审裁定。

对 fp_screen 之后 fp_decision=keep 的每条 finding 生成一张对抗复核卡：
  prosecution（控方）：支持判定的原文证据（逐字 quote、证据种类、外部记录）；
  defense（辩方）：可能的善意解释 / 学科惯例（由类型与 context_flags 确定性生成）；
  ruling（裁定）：维持 / 降级 / 待复核 + 一句理由。

裁定纪律（确定性规则 A1–A5；A4 建议性条目优先，因其不是判定）：
  A4  category=suggestion → 维持 info（不进入待复核）
  A1  已标待复核 / 证据种类为 model_inference|none → 待复核
  A2  critical 但无 external_record → 降级 major（critical 必须有外部记录）
  A3  诚信类（fabrication_suspected/integrity 等）无 external_record → 降级 major + 待复核
  A5  其余（有逐字 quote 或外部记录支撑）→ 维持

输出 adjudication.json：最终 findings（含 ruling 后严重度）+ 全部复核卡，
供 Agent 终审直接采用或覆写（覆写必须写理由）。

用法：
  python3 adjudicate.py --input screened.json --output adjudication.json

缺键不崩，exit 0。
"""
import argparse
import json
import sys

SEVERITY_ORDER = ["info", "minor", "major", "critical"]
INTEGRITY_TYPES = {
    "fabrication_suspected",
    "integrity",
    "plagiarism_suspected",
    "duplicate_publication",
    "image_manipulation",
    "image_reuse",
    "data_fabrication",
    "authorship_misconduct",
}

# 辩方善意解释模板（按 finding type；缺省用通用模板）
DEFENSE_TEMPLATES = {
    "metadata_mismatch": "可能是出版社著录版本差异或数据库录入延迟，需以 DOI 登记信息为准。",
    "reference_error": "可能是排版/著录疏忽而非故意错误，作者自查即可修正。",
    "reference_style": "可能是期刊允许范围内的体例选择或编辑统一调整。",
    "missing_ethics": "可能期刊投稿流程中另行收集伦理批件，正文省略属刊方惯例。",
    "ethics_statement_missing": "可能期刊投稿流程中另行收集伦理批件，正文省略属刊方惯例。",
    "statistics_error": "可能是四舍五入或报告口径差异，需原始数据复算确认。",
    "figure_issue": "可能是分辨率或排版损失导致的视觉差异，需原始图件核对。",
    "fact_error": "可能是术语口径或版本差异，需对照所引来源原文确认。",
    "unsupported_claim": "可能作者掌握未公开的补充材料，但正文未呈现即属证据不足。",
}
DEFAULT_DEFENSE = "可能存在未体现在正文中的合理背景（数据版本、刊方流程、学科惯例），需作者回应确认。"


def cap(sev, ceiling):
    if sev in SEVERITY_ORDER and SEVERITY_ORDER.index(sev) > SEVERITY_ORDER.index(ceiling):
        return ceiling
    return sev


def build_card(finding):
    fid = str(finding.get("id") or "unknown")
    ftype = str(finding.get("type") or "unspecified")
    category = str(finding.get("category") or "insufficient_evidence")
    severity = str(finding.get("severity") or "minor")
    evidence_kind = str(finding.get("evidence_kind") or "none")
    quote = str(finding.get("quote") or "").strip()
    status = str(finding.get("verdict_status") or "确认")
    evidence = finding.get("evidence")
    evidence_text = evidence if isinstance(evidence, str) else ""

    prosecution_items = []
    if quote:
        prosecution_items.append("原文逐字摘录：%s" % quote[:300])
    if evidence_kind == "external_record":
        prosecution_items.append("外部数据库记录支持该判定。")
    elif evidence_kind == "local_rule":
        prosecution_items.append("命中本地规则：%s" % (evidence_text or "（规则名未给出）"))
    elif evidence_kind == "verbatim_quote" and quote:
        prosecution_items.append("证据种类为逐字摘录，可指回原文位置。")
    if evidence_text and evidence_kind != "local_rule":
        prosecution_items.append("依据：%s" % evidence_text[:300])
    if not prosecution_items:
        prosecution_items.append("（无可用原文证据，仅凭模型推断。）")

    defense_items = [DEFENSE_TEMPLATES.get(ftype, DEFAULT_DEFENSE)]
    flags = finding.get("context_flags")
    if isinstance(flags, dict) and flags.get("benign_explanation"):
        defense_items.append(str(flags["benign_explanation"]))

    # ---- 裁定纪律 A1–A5 ----
    # 建议性条目优先走 A4：建议不是判定，无需证据也不进待复核。
    new_severity = severity
    if category == "suggestion":
        new_severity = "info"
        ruling, reason, rule = ("维持", "建议性条目，维持 info，不进入违规判定。", "A4")
    elif ftype in INTEGRITY_TYPES and evidence_kind != "external_record":
        # A3 先于 A1/A2：诚信类给出更具体的裁定理由
        new_severity = cap(severity, "major")
        ruling, reason, rule = (
            "待复核",
            "诚信类指控缺外部记录双信号，封顶 major 并待复核，禁止单方定案。",
            "A3",
        )
    elif status == "待复核" or evidence_kind in ("model_inference", "none"):
        ruling, reason, rule = (
            "待复核",
            "证据强度不足（%s），裁定前须补可核对证据。" % evidence_kind,
            "A1",
        )
    elif severity == "critical" and evidence_kind != "external_record":
        new_severity = "major"
        ruling, reason, rule = (
            "降级",
            "critical 判定必须有 external_record 支撑，当前证据最高支撑 major。",
            "A2",
        )
    else:
        ruling, reason, rule = (
            "维持",
            "判定强度与证据强度匹配（%s / %s）。" % (severity, evidence_kind),
            "A5",
        )

    card = {
        "finding_id": fid,
        "type": ftype,
        "prosecution": prosecution_items,
        "defense": defense_items,
        "ruling": ruling,
        "ruling_rule": rule,
        "ruling_reason": reason,
        "severity_before": severity,
        "severity_after": new_severity,
    }
    return card, ruling, new_severity


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="对抗式复核：为 keep 的 findings 生成控辩复核卡并给出终审裁定。"
    )
    parser.add_argument("--input", required=True, help="fp_screen 输出 JSON 路径")
    parser.add_argument("--output", required=True, help="adjudication.json 输出路径")
    args = parser.parse_args(argv)

    result = {
        "note": "adjudicate 输出：对抗复核卡 + 终审裁定后的最终 findings",
        "findings": [],
        "adjudication_cards": [],
        "adjudication_errors": [],
        "summary": {},
    }

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        result["adjudication_errors"].append("读取输入失败: %s" % exc)
        data = {}

    findings = []
    if isinstance(data, dict):
        findings = data.get("findings") or []
    elif isinstance(data, list):
        findings = data
    if not isinstance(findings, list):
        result["adjudication_errors"].append("findings 字段不是列表，按空处理")
        findings = []

    final = []
    cards = []
    n_upheld = n_downgraded = n_pending = n_dropped = 0
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        f = dict(finding)
        if f.get("fp_decision") == "drop":
            n_dropped += 1
            final.append(f)  # 保留在输出中供审计，但不生成复核卡
            continue
        try:
            card, ruling, new_severity = build_card(f)
        except Exception as exc:
            result["adjudication_errors"].append(
                "%s 复核卡生成失败: %s" % (f.get("id", "?"), exc)
            )
            final.append(f)
            continue
        cards.append(card)
        f["severity"] = new_severity
        f["ruling"] = ruling
        f["ruling_reason"] = card["ruling_reason"]
        if ruling == "待复核":
            f["verdict_status"] = "待复核"
            n_pending += 1
        elif ruling == "降级":
            n_downgraded += 1
        else:
            n_upheld += 1
        final.append(f)

    result["findings"] = final
    result["adjudication_cards"] = cards
    result["summary"] = {
        "total": len(final),
        "upheld": n_upheld,
        "downgraded": n_downgraded,
        "pending_review": n_pending,
        "dropped_by_fp_screen": n_dropped,
    }

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("写入输出失败: %s" % exc, file=sys.stderr)

    print(
        "adjudicate: 复核卡 %d 张（维持 %d / 降级 %d / 待复核 %d），fp_screen 已排除 %d 条"
        % (len(cards), n_upheld, n_downgraded, n_pending, n_dropped)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
