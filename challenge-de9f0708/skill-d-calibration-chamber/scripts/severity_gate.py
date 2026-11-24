#!/usr/bin/env python3
"""severity_gate.py — 严重度规则引擎（判定强度与证据强度匹配的机械闸门）。

输入一份 findings 草稿 JSON，对每条 finding 按确定性规则执行严重度封顶 /
降级 / 转待复核，并把逐条触发的规则记录进 audit_trail，输出闸门后的
findings 与降级日志。

规则总览（R1–R8，详见 references/severity_rubric.md）：
  R1  evidence_kind ∈ {model_inference, none} → 严重度封顶 minor
  R2  evidence_kind ∈ {model_inference, none} → verdict_status := 待复核
  R3  type ∈ INTEGRITY_TYPES 且无 external_record 信号 → 封顶 major + 待复核
  R4  evidence_kind=verbatim_quote 但 quote 为空 → 视为 model_inference（重跑 R1/R2）
  R5  category=suggestion → 封顶 info
  R6  evidence_kind=local_rule 单信号且无 quote → 封顶 minor
  R7  evidence_kind=verbatim_quote → 最低 minor（不抬升更高）
  R8  其他 → 保持（需 verbatim_quote / external_record 支撑 major/critical）

用法：
  python3 severity_gate.py --input findings_draft.json --output gated.json \
      --log downgrade_log.json

输入 JSON 结构（缺键不崩，一律按空处理）：
  {"findings": [ {"id": ..., "type": ..., "category": ...,
                  "claimed_severity": "critical|major|minor|info",
                  "evidence_kind": "verbatim_quote|external_record|local_rule|model_inference|none",
                  "quote": "...", "context_flags": {...}, ...}, ... ]}

退出码恒为 0；错误信息写入输出的 gate_errors 字段。
"""
import argparse
import json
import sys

SEVERITY_ORDER = ["info", "minor", "major", "critical"]
KNOWN_SEVERITIES = set(SEVERITY_ORDER)
KNOWN_EVIDENCE_KINDS = {
    "verbatim_quote",
    "external_record",
    "local_rule",
    "model_inference",
    "none",
}
# 学术诚信 / 捏造嫌疑类：判高严重度必须有外部记录支撑
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
VALID_CATEGORIES = {"fact_error", "insufficient_evidence", "norm_issue", "suggestion"}


def norm_severity(value):
    """把任意输入规整为合法严重度，未知值按 minor 处理。"""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in KNOWN_SEVERITIES:
            return v
    return "minor"


def norm_evidence_kind(value):
    if isinstance(value, str):
        v = value.strip().lower()
        if v in KNOWN_EVIDENCE_KINDS:
            return v
    return "none"


def sev_idx(s):
    return SEVERITY_ORDER.index(s)


def cap_severity(current, cap):
    """返回 (新严重度, 是否被压低)。"""
    return (cap, True) if sev_idx(current) > sev_idx(cap) else (current, False)


def raise_severity(current, floor):
    return (floor, True) if sev_idx(current) < sev_idx(floor) else (current, False)


def has_external_signal(finding):
    """external_record 信号：evidence_kind 本身或 context_flags.external_record。"""
    flags = finding.get("context_flags")
    if not isinstance(flags, dict):
        flags = {}
    return norm_evidence_kind(finding.get("evidence_kind")) == "external_record" or bool(
        flags.get("external_record")
    )


def process_finding(finding, index):
    """对单条 finding 跑 R1–R8，返回 (新 finding, 审计记录列表)。"""
    if not isinstance(finding, dict):
        finding = {}
    f = dict(finding)
    fid = f.get("id") or "finding-%03d" % (index + 1)
    f["id"] = fid
    ftype = str(f.get("type") or "unspecified")
    f["type"] = ftype
    category = str(f.get("category") or "").strip().lower()
    if category not in VALID_CATEGORIES:
        category = "insufficient_evidence"
    f["category"] = category

    claimed = norm_severity(f.get("claimed_severity", f.get("severity")))
    evidence_kind = norm_evidence_kind(f.get("evidence_kind"))
    quote = f.get("quote")
    if not isinstance(quote, str):
        quote = ""
    quote = quote.strip()
    f["quote"] = quote
    f["evidence_kind"] = evidence_kind
    f["claimed_severity"] = claimed

    audit = []

    def log(rule, action, detail):
        audit.append(
            {
                "finding_id": fid,
                "rule": rule,
                "action": action,
                "detail": detail,
            }
        )

    # R4: 声称逐字摘录但 quote 为空 → 证据种类降级为 model_inference
    if evidence_kind == "verbatim_quote" and not quote:
        evidence_kind = "model_inference"
        f["evidence_kind"] = evidence_kind
        log(
            "R4_empty_quote",
            "evidence_downgrade",
            "evidence_kind=verbatim_quote 但 quote 为空，按 model_inference 处理",
        )

    severity = claimed
    status = str(f.get("verdict_status") or "确认")
    reasons = []

    # R3: 诚信/捏造类无外部记录双信号 → 封顶 major + 待复核（先于 R1，二者取更严）
    if ftype in INTEGRITY_TYPES and not has_external_signal(f):
        severity, changed = cap_severity(severity, "major")
        if changed:
            log(
                "R3_integrity_needs_external",
                "severity_cap",
                "%s 类指控无 external_record 双信号，严重度封顶 major（原 %s）"
                % (ftype, claimed),
            )
        else:
            log(
                "R3_integrity_needs_external",
                "status_flag",
                "%s 类指控无 external_record 双信号" % ftype,
            )
        if status != "待复核":
            status = "待复核"
        reasons.append("诚信类指控缺少外部数据库记录，需联网核验后方可确认")

    # R1 + R2: 推断/无证据 → 封顶 minor 且待复核
    if evidence_kind in ("model_inference", "none"):
        severity, changed = cap_severity(severity, "minor")
        log(
            "R1_inference_cap",
            "severity_cap" if changed else "severity_ok",
            "evidence_kind=%s，严重度封顶 minor（%s → %s）"
            % (evidence_kind, claimed, severity),
        )
        if category != "suggestion":
            # 建议性条目不是判定，无需待复核（R2 豁免）
            if status != "待复核":
                status = "待复核"
                log(
                    "R2_inference_pending",
                    "status_pending",
                    "evidence_kind=%s，判定转待复核" % evidence_kind,
                )
            reasons.append("判定仅基于模型推断或无证据，须人工/外部核验")

    # R5: 建议性条目 → 封顶 info
    if category == "suggestion":
        severity, changed = cap_severity(severity, "info")
        log(
            "R5_suggestion_info",
            "severity_cap" if changed else "severity_ok",
            "category=suggestion，严重度封顶 info（%s → %s）" % (claimed, severity),
        )

    # R6: 本地规则单信号且无 quote → 封顶 minor
    if evidence_kind == "local_rule" and not quote:
        severity, changed = cap_severity(severity, "minor")
        log(
            "R6_local_rule_single_signal",
            "severity_cap" if changed else "severity_ok",
            "evidence_kind=local_rule 且无逐字 quote，严重度封顶 minor（→ %s）" % severity,
        )

    # R7: 有逐字摘录 → 严重度下限 minor（只抬升到 minor，不抬升更高）
    if evidence_kind == "verbatim_quote" and quote:
        severity, changed = raise_severity(severity, "minor")
        if changed:
            log(
                "R7_verbatim_floor",
                "severity_floor",
                "有逐字摘录支撑，严重度不低于 minor（→ %s）" % severity,
            )

    if not audit:
        log(
            "R8_keep",
            "keep",
            "严重度 %s 与证据种类 %s 匹配，无需调整" % (severity, evidence_kind),
        )

    f["severity"] = severity
    f["verdict_status"] = status
    if reasons:
        prev = f.get("pending_reason")
        f["pending_reason"] = "；".join(reasons + ([prev] if prev else []))
    f["severity_adjusted"] = severity != claimed
    return f, audit


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="严重度规则引擎：按证据强度对 findings 执行封顶/降级/待复核，输出审计轨迹。"
    )
    parser.add_argument("--input", required=True, help="findings 草稿 JSON 路径")
    parser.add_argument("--output", required=True, help="闸门后 findings JSON 输出路径")
    parser.add_argument(
        "--log", default=None, help="降级/审计日志 JSON 输出路径（默认 <output>.audit.json）"
    )
    args = parser.parse_args(argv)

    result = {
        "note": "severity_gate 输出：严重度经规则引擎 R1–R8 校准",
        "findings": [],
        "audit_trail": [],
        "gate_errors": [],
        "summary": {},
    }

    try:
        with open(args.input, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:  # 缺文件/坏 JSON 不崩
        result["gate_errors"].append("读取输入失败: %s" % exc)
        data = {}

    findings = []
    if isinstance(data, dict):
        findings = data.get("findings") or []
    elif isinstance(data, list):
        findings = data
    if not isinstance(findings, list):
        result["gate_errors"].append("findings 字段不是列表，按空处理")
        findings = []

    out_findings = []
    audit_all = []
    n_adjusted = n_pending = 0
    for i, finding in enumerate(findings):
        try:
            nf, audit = process_finding(finding, i)
        except Exception as exc:  # 单条坏数据不拖垮整体
            nf = finding if isinstance(finding, dict) else {}
            nf.setdefault("id", "finding-%03d" % (i + 1))
            audit = [
                {
                    "finding_id": nf["id"],
                    "rule": "ERROR",
                    "action": "passthrough",
                    "detail": "处理异常，原样通过: %s" % exc,
                }
            ]
        out_findings.append(nf)
        audit_all.extend(audit)
        if nf.get("severity_adjusted"):
            n_adjusted += 1
        if nf.get("verdict_status") == "待复核":
            n_pending += 1

    result["findings"] = out_findings
    result["audit_trail"] = audit_all
    result["summary"] = {
        "total": len(out_findings),
        "severity_adjusted": n_adjusted,
        "pending_review": n_pending,
        "rules_triggered": len([a for a in audit_all if a["rule"] != "R8_keep"]),
    }

    try:
        with open(args.output, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        print("写入输出失败: %s" % exc, file=sys.stderr)

    log_path = args.log or (args.output + ".audit.json")
    try:
        with open(log_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "note": "severity_gate 降级/审计日志",
                    "audit_trail": audit_all,
                    "summary": result["summary"],
                },
                fh,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as exc:
        print("写入日志失败: %s" % exc, file=sys.stderr)

    print(
        "severity_gate: %d 条 finding，%d 条严重度被调整，%d 条转待复核"
        % (len(out_findings), n_adjusted, n_pending)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
