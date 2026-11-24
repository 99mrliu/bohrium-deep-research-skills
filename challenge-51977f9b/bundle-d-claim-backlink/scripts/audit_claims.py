#!/usr/bin/env python3
"""audit_claims.py — 论断回链审计引擎（本 bundle 签名脚本）。

逐条核验 claims.jsonl 中的论断是否回链到 spans.json 中可机器解析的证据位置：
  C1 schema 完整、strength 取值合法（fact|inference|uncertain）；
  C2 quote 必须是指定 span 文本的 verbatim 子串（规范化连续空白后比对），
     找不到时给出该 span 内最相似行提示；
  C3 span_id 必须存在于 spans.json（悬空引用即违规）；
  C4 strength=fact 必须至少有 1 条通过 C2 的证据；
  C5 strength=inference 必须至少有 1 条通过 C2 的证据，且 text 不得含断定词；
  C6 uncertain 允许 0 证据，但必须在 note 或 text 中说明不确定原因；
  C7 孤儿证据报告：--extractions 中被提取却从未被任何 claim 引用的 span
     → 仅警告，不阻断。
C1–C6 违规 → exit 3；输入文件缺失/无法解析 → exit 2；全部通过 → exit 0。

机器只保证"字面回链"与"强度措辞边界"；论断与证据的语义匹配是模型职责，
应在 result.json.checks 中如实声明这一边界。
"""
import argparse
import difflib
import json
import re
import sys

STRENGTHS = ("fact", "inference", "uncertain")
# 断定词表（C5）：inference 论断不得使用。references/claim_strength.md 列全。
FIRM_WORDS = ("证实", "证明", "确定了", "因果")
# 不确定原因提示词（C6）：uncertain 无证据时，note 非空或 text 含其一即视为已说明原因。
UNCERTAINTY_REASON_WORDS = (
    "缺乏", "不足", "有限", "不一致", "无法确定", "未能", "尚不", "未明", "原因",
)

EVIDENCE_KEYS = ("record_id", "span_id", "quote")
CLAIM_KEYS = ("claim_id", "text", "strength", "evidence")


def normalize_ws(s):
    """规范化连续空白（含换行）为单个空格后去首尾空白。"""
    return re.sub(r"\s+", " ", s).strip()


def fail_input(msg):
    print(f"[E-INPUT] {msg}", file=sys.stderr)
    sys.exit(2)


def load_json(path, what):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        fail_input(f"无法读取{what} {path}：{e}")
    except json.JSONDecodeError as e:
        fail_input(f"{what}不是合法 JSON：{path}：{e}")


def load_jsonl(path, what):
    rows = []
    try:
        with open(path, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    fail_input(f"{what}第 {ln} 行不是合法 JSON：{e}（{path}）")
    except OSError as e:
        fail_input(f"无法读取{what} {path}：{e}")
    return rows


def best_match_line(span_text, quote):
    """在 span 内找与 quote 最相似的一行，作为重取 quote 的提示。"""
    nq = normalize_ws(quote)
    best_line, best_ratio = "", 0.0
    for line in span_text.splitlines():
        nl = normalize_ws(line)
        if not nl:
            continue
        r = difflib.SequenceMatcher(None, nq, nl).ratio()
        if r > best_ratio:
            best_ratio, best_line = r, nl
    if best_line:
        short = best_line if len(best_line) <= 80 else best_line[:77] + "..."
        return f"该 span 内最相似行（相似度 {best_ratio:.2f}）：{short}"
    return "该 span 内没有可比对的有效行。"


def check_claim(claim, spans):
    """返回 (checks dict, violations list, evidence_total, evidence_valid)。"""
    cid = claim.get("claim_id", "<无 claim_id>") if isinstance(claim, dict) else "<非对象行>"
    checks = {c: "skip" for c in ("C1", "C2", "C3", "C4", "C5", "C6")}
    violations = []
    evidence_total = 0
    evidence_valid = 0

    # ---- C1 schema ----
    if not isinstance(claim, dict):
        violations.append({"claim_id": cid, "code": "C1",
                           "message": "C1 违规：claim 行不是 JSON 对象。"})
        checks["C1"] = "fail"
        return checks, violations, evidence_total, evidence_valid
    missing = [k for k in CLAIM_KEYS if k not in claim]
    schema_ok = not missing
    if schema_ok:
        if not isinstance(claim["claim_id"], str) or not claim["claim_id"].strip():
            schema_ok = False
        elif not isinstance(claim["text"], str) or not claim["text"].strip():
            schema_ok = False
        elif claim["strength"] not in STRENGTHS:
            violations.append({"claim_id": cid, "code": "C1",
                               "message": f"C1 违规：strength 取值非法：{claim['strength']!r}，"
                                          "只允许 fact|inference|uncertain。"})
            checks["C1"] = "fail"
            return checks, violations, evidence_total, evidence_valid
        elif not isinstance(claim["evidence"], list):
            schema_ok = False
        else:
            for i, ev in enumerate(claim["evidence"]):
                if not isinstance(ev, dict) or any(k not in ev for k in EVIDENCE_KEYS):
                    violations.append({"claim_id": cid, "code": "C1",
                                       "message": f"C1 违规：evidence[{i}] 缺少字段 "
                                                  f"{[k for k in EVIDENCE_KEYS if not isinstance(ev, dict) or k not in ev]}。"})
                    checks["C1"] = "fail"
                    return checks, violations, evidence_total, evidence_valid
    if not schema_ok:
        detail = f"缺少字段 {missing}" if missing else "字段类型非法"
        violations.append({"claim_id": cid, "code": "C1",
                           "message": f"C1 违规：schema 不完整（{detail}）。"})
        checks["C1"] = "fail"
        return checks, violations, evidence_total, evidence_valid
    checks["C1"] = "pass"

    strength = claim["strength"]
    text = claim["text"]
    note = claim.get("note", "") or ""
    evidence = claim["evidence"]
    evidence_total = len(evidence)

    # ---- C3 悬空引用 + C2 回链核验 ----
    c3_ok = True
    c2_ok = True
    for i, ev in enumerate(evidence):
        sid = ev["span_id"]
        if sid not in spans:
            c3_ok = False
            violations.append({"claim_id": cid, "code": "C3",
                               "message": f"C3 违规：evidence[{i}] 的 span_id {sid!r} "
                                          "不存在于 spans.json（悬空引用），请先运行 index_sources.py 并核对定位。"})
            continue
        span_text = spans[sid]["text"]
        if normalize_ws(ev["quote"]) in normalize_ws(span_text):
            evidence_valid += 1
        else:
            c2_ok = False
            hint = best_match_line(span_text, ev["quote"])
            violations.append({"claim_id": cid, "code": "C2",
                               "message": f"C2 违规：evidence[{i}] 的 quote 不是 span {sid} 的 "
                                          "verbatim 子串。请回到原文重取 quote，禁止凭记忆改写。"
                                          f"{hint}"})
    checks["C3"] = "pass" if c3_ok else "fail"
    checks["C2"] = "pass" if (c2_ok and c3_ok) else ("fail" if not c2_ok else "skip")

    # ---- C4 fact 必须有有效证据 ----
    if strength == "fact":
        if evidence_valid >= 1:
            checks["C4"] = "pass"
        else:
            checks["C4"] = "fail"
            violations.append({"claim_id": cid, "code": "C4",
                               "message": "C4 违规：strength=fact 的论断没有 1 条通过 C2 的证据；"
                                          "无证据的'事实'论断不许出厂，请补证据或降级为 uncertain。"})

    # ---- C5 inference 措辞与证据 ----
    if strength == "inference":
        hit = [w for w in FIRM_WORDS if w in text]
        if evidence_valid < 1:
            checks["C5"] = "fail"
            violations.append({"claim_id": cid, "code": "C5",
                               "message": "C5 违规：strength=inference 的论断没有 1 条通过 C2 的证据。"})
        elif hit:
            checks["C5"] = "fail"
            violations.append({"claim_id": cid, "code": "C5",
                               "message": f"C5 违规：inference 论断含断定词 {hit}（断定词表："
                                          f"{'|'.join(FIRM_WORDS)}）；请改用推断词（提示|可能|关联等）"
                                          "或把 strength 降级为 uncertain 并说明原因。"})
        else:
            checks["C5"] = "pass"

    # ---- C6 uncertain 须说明原因 ----
    if strength == "uncertain":
        if evidence_total >= 1 or note.strip():
            checks["C6"] = "pass"
        else:
            reason_hit = [w for w in UNCERTAINTY_REASON_WORDS if w in text]
            if reason_hit:
                checks["C6"] = "pass"
            else:
                checks["C6"] = "fail"
                violations.append({"claim_id": cid, "code": "C6",
                                   "message": "C6 违规：uncertain 论断无证据且未在 note 或 text 中说明"
                                              "不确定原因（如：证据有限/结果不一致/无法确定）。"})
    return checks, violations, evidence_total, evidence_valid


def main():
    ap = argparse.ArgumentParser(
        description="论断回链审计：核验 claims.jsonl 每条论断的 quote 是否为指定 span 的 verbatim 子串，"
                    "并检查强度标签与证据匹配（规则 C1–C7）。")
    ap.add_argument("--claims", required=True, help="claims.jsonl 路径")
    ap.add_argument("--spans", required=True, help="index_sources.py 输出的 spans.json")
    ap.add_argument("--out", required=True, help="输出 audit_report.json 路径")
    ap.add_argument("--extractions", default=None,
                    help="可选：extractions.jsonl（C7 孤儿证据报告）")
    ap.add_argument("--conflicts", default=None,
                    help="可选：conflicts.jsonl（{topic,claim_id_a,claim_id_b,nature}，冲突证据登记）")
    args = ap.parse_args()

    spans_doc = load_json(args.spans, "spans.json")
    if not isinstance(spans_doc, dict):
        fail_input("spans.json 顶层必须是对象。")
    spans = {k: v for k, v in spans_doc.items() if not k.startswith("__")}
    if not spans:
        fail_input(f"spans.json 不含任何 span（{args.spans}），请先运行 index_sources.py。")
    for sid, sp in spans.items():
        if not isinstance(sp, dict) or "text" not in sp:
            fail_input(f"spans.json 中 span {sid!r} 缺少 text 字段，文件疑似损坏。")

    claims = load_jsonl(args.claims, "claims.jsonl")
    if not claims:
        fail_input(f"claims.jsonl 为空（{args.claims}）：没有可审计的论断，"
                   "请先按工作流程登记论断再审计。")

    report_claims = []
    all_violations = []
    for claim in claims:
        checks, violations, ev_total, ev_valid = check_claim(claim, spans)
        cid = claim.get("claim_id", "<无 claim_id>") if isinstance(claim, dict) else "<非对象行>"
        report_claims.append({
            "claim_id": cid,
            "strength": claim.get("strength") if isinstance(claim, dict) else None,
            "section": claim.get("section", "") if isinstance(claim, dict) else "",
            "evidence_total": ev_total,
            "evidence_valid": ev_valid,
            "checks": checks,
            "violation_codes": [v["code"] for v in violations],
        })
        all_violations.extend(violations)

    # ---- C7 孤儿证据（警告，不阻断） ----
    orphans = []
    if args.extractions:
        cited = set()
        for claim in claims:
            if isinstance(claim, dict) and isinstance(claim.get("evidence"), list):
                for ev in claim["evidence"]:
                    if isinstance(ev, dict) and "span_id" in ev:
                        cited.add(ev["span_id"])
        for row in load_jsonl(args.extractions, "extractions.jsonl"):
            if not isinstance(row, dict):
                continue
            if row.get("status", "extracted") != "extracted":
                continue
            sid = row.get("span_id", "")
            if sid not in spans:
                print(f"[W-ORPHAN] extractions 引用了不存在的 span {sid!r}（悬空提取，请核对）。",
                      file=sys.stderr)
                continue
            if sid not in cited:
                orphans.append({
                    "span_id": sid,
                    "record_id": row.get("record_id", ""),
                    "note": row.get("note", ""),
                    "text_preview": normalize_ws(spans[sid]["text"])[:80],
                })

    # ---- 冲突证据登记 ----
    conflicts = []
    if args.conflicts:
        by_id = {c.get("claim_id"): c for c in claims if isinstance(c, dict)}
        valid_by_id = {c["claim_id"]: c["evidence_valid"] for c in report_claims}
        for row in load_jsonl(args.conflicts, "conflicts.jsonl"):
            if not isinstance(row, dict):
                continue
            entry = {
                "topic": row.get("topic", ""),
                "claim_id_a": row.get("claim_id_a", ""),
                "claim_id_b": row.get("claim_id_b", ""),
                "nature": row.get("nature", ""),
            }
            problems = []
            for key in ("claim_id_a", "claim_id_b"):
                cid = entry[key]
                if cid not in by_id:
                    problems.append(f"{key}={cid!r} 不在 claims.jsonl 中")
                elif valid_by_id.get(cid, 0) < 1:
                    problems.append(f"{key}={cid!r} 没有通过 C2 的证据")
            if problems:
                entry["status"] = "rejected"
                entry["reason"] = "；".join(problems)
                print(f"[W-CONFLICT] 冲突登记被拒绝（{'；'.join(problems)}），"
                      "冲突双方都必须有回链证据。", file=sys.stderr)
            else:
                entry["status"] = "registered"
            conflicts.append(entry)

    report = {
        "tool": "audit_claims.py",
        "rules": {
            "C1": "schema 完整、strength 取值合法",
            "C2": "quote 为指定 span 的 verbatim 子串（规范化连续空白后比对）",
            "C3": "span_id 必须存在于 spans.json",
            "C4": "fact 必须 ≥1 条通过 C2 的证据",
            "C5": "inference 必须 ≥1 条通过 C2 的证据且不得含断定词",
            "C6": "uncertain 允许 0 证据但须说明不确定原因",
            "C7": "孤儿证据仅警告不阻断",
            "firm_words": list(FIRM_WORDS),
        },
        "summary": {
            "claims_total": len(report_claims),
            "claims_passed": sum(1 for c in report_claims if not c["violation_codes"]),
            "claims_failed": sum(1 for c in report_claims if c["violation_codes"]),
            "violations_total": len(all_violations),
            "orphan_spans_total": len(orphans),
            "conflicts_registered": sum(1 for c in conflicts if c["status"] == "registered"),
        },
        "claims": report_claims,
        "violations": all_violations,
        "orphan_spans": orphans,
        "conflicts": conflicts,
        "boundary_note": "机器只核验字面回链与强度措辞边界；论断与证据的语义匹配属模型职责。",
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")

    s = report["summary"]
    print(f"审计完成：论断 {s['claims_total']} 条，通过 {s['claims_passed']} 条，"
          f"违规 {s['claims_failed']} 条；孤儿证据 {s['orphan_spans_total']} 个（警告）；"
          f"冲突登记 {s['conflicts_registered']} 对。")
    if orphans:
        print("[C7 警告] 以下已提取 span 从未被任何论断引用（孤儿证据，不阻断）：")
        for o in orphans:
            print(f"  - {o['span_id']}（{o['record_id']}）{o['note']}")
    if all_violations:
        for v in all_violations:
            print(f"[{v['code']}] {v['claim_id']}：{v['message']}", file=sys.stderr)
        print(f"审计未通过（{len(all_violations)} 处违规），详见 {args.out}。", file=sys.stderr)
        sys.exit(3)
    print("审计通过（exit 0）：所有论断均回链到可机器解析的证据位置。")
    sys.exit(0)


if __name__ == "__main__":
    main()
