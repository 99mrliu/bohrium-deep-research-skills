#!/usr/bin/env python3
"""risk_triage.py — 假阳性风险分级与回译复核清单工具（xlang-hit-evidence-auditor 第二阶段）。

仅使用 Python 3.8+ 标准库；确定性、离线。本脚本不做机器翻译，也不替 Agent 下
复核结论：它负责 (a) 按确定性启发式给每条命中打风险档并说明理由，
(b) 按分层抽检策略生成回译复核任务清单（含待回译术语、原文片段、空判定模板），
(c) 读回 Agent 按清单填写的复核结论，做依据完整性校验（凡 confirmed /
false_positive 必须有非空 basis，否则报错且退出码为 2），合并进台账并输出
最终台账与统计。

子命令
------
triage   读 evidence_ledger.json → 风险分级 → 写 backtranslation_queue.json
         与带风险标注的台账；高风险全检、中风险确定性抽样、低风险记录免检理由。
ingest   读 evidence_ledger.json + Agent 填好的 backtranslation_queue.json →
         校验判定与依据 → 合并 → 写 /app/output 用的最终台账、统计与
         result.json（若提供 --case，镜像 output_contract 全部字段）。

用法
----
    python3 risk_triage.py triage [--ledger /app/work/evidence_ledger.json] \
        [--workdir /app/work] [--rules rules.json] [--medium-sample 0.5] \
        [--max-queue 20]
    python3 risk_triage.py ingest [--ledger /app/work/evidence_ledger.json] \
        [--queue /app/work/backtranslation_queue.json] [--out /app/output] \
        [--case /input/case.json] [--workdir /app/work]

triage 退出码恒为 0；ingest 校验失败退出码为 2 且不写最终产物。
"""
import argparse
import json
import sys
import time
from pathlib import Path

# ----------------------------------------------------------------------------- 默认规则

DEFAULT_RULES = {
    # 命中级/概念级标记 → 风险档。判据语义见 rules/audit_policy.md。
    "high_flags": ["wording_mismatch", "abbrev_only", "no_surface_match",
                   "secondary_source"],
    "medium_flags": ["context_terms_absent", "title_only", "short_form",
                     "partial_coverage", "translation_record",
                     "language_uncertain"],
    "medium_sample": 0.5,      # 中风险抽样比例（确定性等距抽样）
    "max_queue": 20,           # 复核队列上限（64 次模型请求预算下的保守值）
    "abbrev_note": "仅由缩写词形命中的概念证据视为高风险（缩写跨语种歧义）",
}

VERDICTS = ("confirmed", "false_positive", "undetermined")

# ----------------------------------------------------------------------------- 工具


def load_json(path, what, errors):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append("无法读取 %s (%s): %s" % (what, path, exc))
        return None


def load_rules(path, log):
    rules = dict(DEFAULT_RULES)
    if path:
        user = load_json(path, "规则文件", [])
        if isinstance(user, dict):
            rules.update(user)
            log.append("rules overridden from %s: keys %s"
                       % (path, sorted(user.keys())))
    return rules

# ----------------------------------------------------------------------------- 风险分级


def assess_hit(hit, rules):
    """返回 (risk, reasons)。high > medium > low，全部理由留痕。"""
    high_flags = set(rules["high_flags"])
    medium_flags = set(rules["medium_flags"])
    reasons_high, reasons_med = [], []
    evs = hit.get("concept_evidence") or []

    if evs and all(e.get("no_surface_match") for e in evs):
        reasons_high.append("no_surface_match: 所有查询概念在该记录的标题/摘要/正文中"
                            "均无原文表面命中，命中依据不明（疑似仅靠二手元数据或机翻词面）")
    for e in evs:
        cid = e.get("concept_id")
        flags = set(e.get("flags") or [])
        if e.get("wording_mismatch") and "wording_mismatch" in high_flags:
            reasons_high.append("wording_mismatch[%s]: %s"
                                % (cid, e.get("wording_mismatch_detail",
                                              "仅译文词形命中，原文无对应用词")))
        if "abbrev_form" in flags and "abbrev_only" in high_flags:
            forms = [m.get("form") for m in e.get("matched_forms", [])][:3]
            reasons_high.append("abbrev_only[%s]: 概念仅由缩写词形 %s 命中，"
                                "同一缩写在不同语种可能指不同概念，需回译核对"
                                % (cid, forms))
        if "context_terms_absent" in flags and "context_terms_absent" in medium_flags:
            reasons_med.append("context_terms_absent[%s]: 概念定义了 context_terms，"
                               "但命中窗口内均未出现，词面对应而上下文语义存疑" % cid)
        if "title_only" in flags and "title_only" in medium_flags:
            reasons_med.append("title_only[%s]: 概念仅在标题命中，无摘要/正文佐证" % cid)
        if "short_form" in flags and "short_form" in medium_flags:
            reasons_med.append("short_form[%s]: 命中词形过短（≤3 字符），子串误配风险" % cid)
    for f in hit.get("flags") or []:
        if f == "secondary_source" and f in high_flags:
            reasons_high.append("secondary_source: 记录类型为二手转述/引用提及，"
                                "概念未在原文一次文献中出现")
        elif f in medium_flags:
            reasons_med.append("%s: 命中级标记" % f)
    matched = sum(1 for e in evs if e.get("matched"))
    if evs and 0 < matched < len(evs) and "partial_coverage" in medium_flags:
        reasons_med.append("partial_coverage: 仅 %d/%d 个概念有表面命中"
                           % (matched, len(evs)))

    if reasons_high:
        return "high", reasons_high + reasons_med
    if reasons_med:
        return "medium", reasons_med
    if not evs:
        return "low", ["no_concepts: 无查询概念可对齐（按低风险记录，不进复核队列）"]
    return "low", ["direct_original_match: 原文语种词形直接命中且无风险标记"]


def pick_medium_sample(medium_ids, frac):
    """确定性等距抽样：对排序后的中风险 hit_id 等距选取 ceil(n*frac) 个。"""
    ids = sorted(medium_ids)
    n = len(ids)
    if n == 0 or frac <= 0:
        return set()
    k = max(1, round(n * frac))
    k = min(k, n)
    step = n / k
    return {ids[int(i * step)] for i in range(k)}

# ----------------------------------------------------------------------------- triage


def cmd_triage(args):
    work_dir = Path(args.workdir)
    work_dir.mkdir(parents=True, exist_ok=True)
    log = ["risk_triage triage started " + time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                         time.gmtime())]
    errors = []
    ledger = load_json(args.ledger, "evidence_ledger.json", errors)
    if ledger is None:
        (work_dir / "risk_triage_log.json").write_text(
            json.dumps(log + errors, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False))
        return 0
    rules = load_rules(args.rules, log)
    if getattr(args, "medium_sample", None) is not None:
        rules["medium_sample"] = args.medium_sample
        log.append("medium_sample overridden by CLI: %s" % args.medium_sample)
    if getattr(args, "max_queue", None) is not None:
        rules["max_queue"] = args.max_queue
        log.append("max_queue overridden by CLI: %s" % args.max_queue)
    q_lang = ledger.get("query_language") or "und"

    queue, n_high, n_med, n_low = [], 0, 0, 0
    medium_ids, medium_risk = [], {}
    assessments = {}
    for hit in ledger.get("hits", []):
        risk, reasons = assess_hit(hit, rules)
        assessments[hit["hit_id"]] = (risk, reasons)
        hit["risk"] = risk
        hit["risk_reasons"] = reasons
        if risk == "high":
            n_high += 1
        elif risk == "medium":
            n_med += 1
            medium_ids.append(hit["hit_id"])
        else:
            n_low += 1
            hit["review"] = {"verdict": "not_reviewed",
                             "exempt_reason": "low_risk: 原文语种词形直接命中且无风险标记；"
                                              "按分层抽检策略低风险免检，理由已记录"}

    sampled_medium = pick_medium_sample(medium_ids, float(rules["medium_sample"]))
    overflow = []
    for hit in ledger.get("hits", []):
        risk = hit["risk"]
        if risk == "high" or (risk == "medium" and hit["hit_id"] in sampled_medium):
            terms = []
            for e in hit.get("concept_evidence") or []:
                if not e.get("matched_forms"):
                    terms.append({"concept_id": e.get("concept_id"),
                                  "matched_form": None,
                                  "form_lang": None,
                                  "target_lang": q_lang,
                                  "note": "原文无表面命中；请核对命中声称的依据是否成立",
                                  "quote": None, "quote_context": None,
                                  "locator": hit.get("locator")})
                    continue
                for m in e["matched_forms"][:2]:
                    terms.append({"concept_id": e.get("concept_id"),
                                  "matched_form": m.get("form"),
                                  "form_lang": m.get("form_lang"),
                                  "target_lang": q_lang,
                                  "quote": m.get("quote"),
                                  "quote_context": m.get("quote_context"),
                                  "locator": m.get("locator"),
                                  "span": m.get("span"), "line": m.get("line")})
            queue.append({
                "queue_id": "q%03d" % (len(queue) + 1),
                "hit_id": hit["hit_id"],
                "risk": risk,
                "risk_reasons": hit["risk_reasons"],
                "hit_language": hit.get("language_effective"),
                "hit_version": hit.get("version"),
                "hit_doi": hit.get("doi"),
                "terms_to_backtranslate": terms,
                "review": {"verdict": None, "back_translation": None,
                           "semantic_consistent": None, "basis": None,
                           "reviewer": None, "reviewed_at": None},
            })
            hit["review"] = {"verdict": "pending", "queue_id": queue[-1]["queue_id"]}
        elif risk == "medium":
            hit["review"] = {"verdict": "not_reviewed",
                             "exempt_reason": "medium_risk_sampling: 中风险按 %.2f 比例"
                                              "确定性等距抽样，本条未被抽中；免检理由已记录"
                                              % float(rules["medium_sample"])}

    max_queue = int(rules["max_queue"])
    if len(queue) > max_queue:
        # 高风险全检优先；裁掉队列尾部的中风险抽样项并记录
        trimmed = []
        kept = []
        for item in queue:
            if len(kept) < max_queue or item["risk"] == "high":
                kept.append(item)
            else:
                trimmed.append(item)
        for item in trimmed:
            for hit in ledger.get("hits", []):
                if hit["hit_id"] == item["hit_id"]:
                    hit["review"] = {"verdict": "not_reviewed",
                                     "exempt_reason": "budget_cap: 复核队列超过 max_queue=%d，"
                                                      "高风险全检优先后本条中风险抽样项被裁减"
                                                      % max_queue}
        overflow = [i["queue_id"] for i in trimmed]
        queue = kept
        for i, item in enumerate(queue):
            item["queue_id"] = "q%03d" % (i + 1)
        log.append("queue trimmed to %d items (max_queue=%d); dropped medium samples: %s"
                   % (len(queue), max_queue, overflow))

    queue_doc = {
        "skill": "xlang-hit-evidence-auditor",
        "stage": "backtranslation_review_queue",
        "case_id": ledger.get("case_id"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query_language": q_lang,
        "instructions": "Agent 按 rules/audit_policy.md 第 3 节检查清单逐条执行受控回译："
                        "把 terms_to_backtranslate 中的 matched_form 回译到查询语种"
                        "（target_lang），与原文 quote_context 比对语义一致性，"
                        "填写 review 块：verdict ∈ confirmed/false_positive/undetermined，"
                        "basis 必填（confirmed/false_positive 缺 basis 校验会报错），"
                        "并保留 back_translation 原文备查。脚本不做机器翻译。",
        "budget": {"queued_items": len(queue),
                   "estimated_model_calls": len(queue),
                   "note": "每条复核项约 1 次模型请求，可多条合并到一次请求以省预算；"
                           "高风险 %d 条全检，中风险抽样 %d/%d 条"
                           % (n_high, len(sampled_medium), n_med)},
        "items": queue,
    }
    (work_dir / "backtranslation_queue.json").write_text(
        json.dumps(queue_doc, ensure_ascii=False, indent=2), encoding="utf-8")
    (work_dir / "evidence_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    stats = {"high": n_high, "medium": n_med, "low": n_low,
             "queued": len(queue), "medium_sampled": len(sampled_medium),
             "medium_exempted": n_med - len(sampled_medium)
                                - sum(1 for i in overflow),
             "queue_overflow_dropped": overflow}
    log.append("triage done: high=%d medium=%d low=%d queued=%d"
               % (n_high, n_med, n_low, len(queue)))
    (work_dir / "risk_triage_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "risk_distribution": stats,
                      "queue": str(work_dir / "backtranslation_queue.json")},
                     ensure_ascii=False))
    return 0

# ----------------------------------------------------------------------------- ingest


def validate_queue(queue_doc):
    """依据完整性校验。返回 (errors, warnings)。"""
    errors, warnings = [], []
    for item in queue_doc.get("items", []):
        qid = item.get("queue_id")
        review = item.get("review") or {}
        verdict = review.get("verdict")
        if verdict is None:
            warnings.append("%s (%s): 未填写复核结论，按 pending 处理"
                            % (qid, item.get("hit_id")))
            continue
        if verdict not in VERDICTS:
            errors.append("%s (%s): verdict=%r 非法，必须为 %s 之一"
                          % (qid, item.get("hit_id"), verdict, "/".join(VERDICTS)))
            continue
        basis = review.get("basis")
        basis_ok = isinstance(basis, str) and basis.strip()
        if verdict in ("confirmed", "false_positive") and not basis_ok:
            errors.append("%s (%s): verdict=%s 必须填写非空 basis（判定依据），"
                          "否则判定不可复核" % (qid, item.get("hit_id"), verdict))
        if verdict == "undetermined" and not basis_ok:
            warnings.append("%s (%s): undetermined 建议填写 basis 说明证据不足的原因"
                            % (qid, item.get("hit_id")))
        if verdict in ("confirmed", "false_positive") \
                and not (isinstance(review.get("back_translation"), str)
                         and review["back_translation"].strip()):
            warnings.append("%s (%s): 建议保留 back_translation 原文备查"
                            % (qid, item.get("hit_id")))
    return errors, warnings


def cmd_ingest(args):
    work_dir = Path(args.workdir)
    work_dir.mkdir(parents=True, exist_ok=True)
    log = ["risk_triage ingest started " + time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                         time.gmtime())]
    errors = []
    ledger = load_json(args.ledger, "evidence_ledger.json", errors)
    queue_doc = load_json(args.queue, "backtranslation_queue.json", errors)
    if ledger is None or queue_doc is None:
        (work_dir / "risk_triage_log.json").write_text(
            json.dumps(log + errors, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False))
        return 2

    verr, vwarn = validate_queue(queue_doc)
    log += ["VALIDATION WARNING: " + w for w in vwarn]
    if verr:
        log += ["VALIDATION ERROR: " + e for e in verr]
        (work_dir / "risk_triage_log.json").write_text(
            json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        # 校验失败：不写最终产物，避免带缺陷的台账进入 /app/output
        print(json.dumps({"status": "validation_failed", "errors": verr,
                          "warnings": vwarn}, ensure_ascii=False))
        return 2

    # 合并复核结论进台账
    by_hit = {}
    pending = 0
    counts = {v: 0 for v in VERDICTS}
    for item in queue_doc.get("items", []):
        review = item.get("review") or {}
        verdict = review.get("verdict")
        by_hit[item.get("hit_id")] = {
            "queue_id": item.get("queue_id"),
            "verdict": verdict or "pending",
            "back_translation": review.get("back_translation"),
            "semantic_consistent": review.get("semantic_consistent"),
            "basis": review.get("basis"),
            "reviewer": review.get("reviewer"),
            "reviewed_at": review.get("reviewed_at"),
        }
        if verdict is None:
            pending += 1
        else:
            counts[verdict] += 1
    for hit in ledger.get("hits", []):
        hid = hit.get("hit_id")
        if hid in by_hit:
            hit["review"] = by_hit[hid]
        elif not isinstance(hit.get("review"), dict):
            hit["review"] = {"verdict": "not_reviewed",
                             "exempt_reason": "未进入复核队列且无免检记录，请检查 triage 日志"}

    risk_dist = {"high": 0, "medium": 0, "low": 0}
    for hit in ledger.get("hits", []):
        risk_dist[hit.get("risk", "low")] = risk_dist.get(hit.get("risk", "low"), 0) + 1
    n_exempt = sum(1 for h in ledger.get("hits", [])
                   if (h.get("review") or {}).get("verdict") == "not_reviewed")
    review_stats = {
        "queued": len(queue_doc.get("items", [])),
        "reviewed": sum(counts.values()),
        "pending": pending,
        "confirmed": counts["confirmed"],
        "false_positive": counts["false_positive"],
        "undetermined": counts["undetermined"],
        "exempt_not_reviewed": n_exempt,
        "validation_warnings": vwarn,
    }
    status = "ok" if pending == 0 else "partial"
    uncertainty = list(ledger.get("uncertainty") or [])
    if pending:
        uncertainty.append("%d 条复核项仍 pending（Agent 未填写结论）；"
                           "对应命中保留为未确认，不计入 confirmed" % pending)
    if counts["undetermined"]:
        uncertainty.append("%d 条命中复核结论为 undetermined（原文不可得/证据不足/"
                           "回译不一致），按约定不计入 confirmed 也不计为假阳性定论"
                           % counts["undetermined"])
    uncertainty += vwarn

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    final_ledger = dict(ledger)
    final_ledger["stage"] = "audit_final"
    final_ledger["uncertainty"] = uncertainty
    (out_dir / "audit_ledger.json").write_text(
        json.dumps(final_ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    stats_doc = {"case_id": ledger.get("case_id"), "status": status,
                 "risk_distribution": risk_dist, "review_stats": review_stats}
    (out_dir / "audit_stats.json").write_text(
        json.dumps(stats_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    # result.json（镜像 output_contract 全字段）
    case, result = None, None
    if args.case and Path(args.case).exists():
        case = load_json(args.case, "case.json", [])
    result = {
        "case_id": ledger.get("case_id") or (case or {}).get("case_id")
                   or "unknown_case",
        "skill": "xlang-hit-evidence-auditor",
        "status": status,
        "query_language": ledger.get("query_language"),
        "hits": ledger.get("hits", []),
        "risk_distribution": risk_dist,
        "review_stats": review_stats,
        "sources": (ledger.get("sources") or [])
                   + [{"file": str(Path(args.queue).resolve())}],
        "uncertainty": uncertainty,
        "change_records": [],
    }
    contract = (case or {}).get("output_contract")
    if isinstance(contract, dict):
        # 有实际产物的契约字段镜像为产物引用，而非置 null
        artifact_map = {"evidence_ledger": str(out_dir / "audit_ledger.json"),
                        "audit_ledger": str(out_dir / "audit_ledger.json"),
                        "audit_stats": str(out_dir / "audit_stats.json")}
        for field in contract:
            if field not in result:
                result[field] = artifact_map.get(field)
        result["output_contract_fields"] = sorted(contract.keys())
        missing = [f for f in contract if result.get(f) is None]
        if missing:
            result["uncertainty"] = result["uncertainty"] + [
                "output_contract 字段 %s 无对应内容，按镜像规则置 null" % missing]
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    log.append("ingest done: status=%s confirmed=%d false_positive=%d "
               "undetermined=%d pending=%d"
               % (status, counts["confirmed"], counts["false_positive"],
                  counts["undetermined"], pending))
    (work_dir / "risk_triage_log.json").write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": status, "risk_distribution": risk_dist,
                      "review_stats": {k: v for k, v in review_stats.items()
                                       if k != "validation_warnings"},
                      "result": str(out_dir / "result.json")}, ensure_ascii=False))
    return 0

# ----------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(
        description="假阳性风险分级与回译复核清单管理（仅标准库、离线；"
                    "不做机器翻译，复核结论由 Agent 按清单填写并经本脚本校验）。")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("triage", help="风险分级并生成回译复核任务清单")
    t.add_argument("--ledger", default="/app/work/evidence_ledger.json")
    t.add_argument("--workdir", default="/app/work")
    t.add_argument("--rules", default=None, help="可选 JSON 规则覆盖文件")
    t.add_argument("--medium-sample", type=float, default=None,
                   help="中风险抽样比例（覆盖规则文件）")
    t.add_argument("--max-queue", type=int, default=None,
                   help="复核队列上限（覆盖规则文件）")
    t.set_defaults(func=cmd_triage)

    g = sub.add_parser("ingest", help="读回 Agent 填好的复核结论，校验并汇总")
    g.add_argument("--ledger", default="/app/work/evidence_ledger.json")
    g.add_argument("--queue", default="/app/work/backtranslation_queue.json")
    g.add_argument("--out", default="/app/output")
    g.add_argument("--case", default="/input/case.json")
    g.add_argument("--workdir", default="/app/work")
    g.set_defaults(func=cmd_ingest)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
