#!/usr/bin/env python3
"""triage.py -- 升级分诊：把必须人工确认的判断从自动判定中分离出来。

输入 decisions.json（JSON 数组，元素含 record_id、decision、reason_code，
可选 boundary_flags 列表、screener_labels 两人标签、evidence_snippet）。
按升级触发器（references/escalation_triggers.md）把记录送入复核队列：

  T1 no_abstract        摘要缺失，模型建议一律降级为待复核
  T2 language_mismatch  语种不符，资格性判断必须人工
  T3 partial_overlap    人群/干预部分重叠的边界情形
  T4 screener_disagreement  两位标注者标签冲突（T4 优先级最高）
  T5 low_evidence       included 建议但无证据片段
  T6 criteria_ambiguous 判定注明标准歧义

优先级：P1=T4 或 T1；P2=T2/T3；P3=T5/T6。自动放行的记录也登记
（confirmation_status=auto_accepted_below_gate），保证队列外也有账。

产物 review_queue.json：{queue:[...], auto_accepted:[...], stats:{...}}。
退出码：0=正常；2=输入缺失或格式不合法。
"""
import argparse
import json
import os
import sys

TRIGGERS = {
    "no_abstract": ("T1", 1),
    "language_mismatch": ("T2", 2),
    "partial_overlap": ("T3", 2),
    "screener_disagreement": ("T4", 1),
    "low_evidence": ("T5", 3),
    "criteria_ambiguous": ("T6", 3),
}


def detect_flags(row):
    flags = list(row.get("boundary_flags") or [])
    labels = row.get("screener_labels") or {}
    if isinstance(labels, dict) and len(labels) >= 2:
        vals = [v for v in labels.values() if v]
        if len(set(vals)) > 1 and "screener_disagreement" not in flags:
            flags.append("screener_disagreement")
    if not row.get("abstract_present", True) and "no_abstract" not in flags:
        flags.append("no_abstract")
    if (row.get("decision") == "included"
            and not row.get("evidence_snippet")
            and "low_evidence" not in flags):
        flags.append("low_evidence")
    return flags


def main():
    ap = argparse.ArgumentParser(description="人工复核升级分诊")
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if not os.path.isfile(args.decisions):
        print("TRIAGE-ERROR: 文件缺失：%s" % args.decisions, file=sys.stderr)
        sys.exit(2)
    try:
        rows = json.load(open(args.decisions, encoding="utf-8"))
    except Exception as exc:
        print("TRIAGE-ERROR: JSON 不合法：%s" % type(exc).__name__, file=sys.stderr)
        sys.exit(2)
    if not isinstance(rows, list):
        print("TRIAGE-ERROR: decisions 必须是数组", file=sys.stderr)
        sys.exit(2)

    queue, auto = [], []
    seen_ids = set()
    for row in rows:
        rid = row.get("record_id")
        if rid is None:
            print("TRIAGE-ERROR: 存在缺 record_id 的判定行", file=sys.stderr)
            sys.exit(2)
        if rid in seen_ids:
            print("TRIAGE-ERROR: record_id 重复：%s" % rid, file=sys.stderr)
            sys.exit(2)
        seen_ids.add(rid)
        flags = detect_flags(row)
        hits = [(f, TRIGGERS[f]) for f in flags if f in TRIGGERS]
        unknown = [f for f in flags if f not in TRIGGERS]
        if hits:
            priority = min(p for _f, (_t, p) in hits)
            queue.append({
                "record_id": rid,
                "model_suggestion": row.get("decision"),
                "suggestion_status": "pending_human_confirmation",
                "queue_reasons": [t for _f, (t, _p) in hits],
                "reason_flags": [f for f, _tf in hits],
                "unmapped_flags": unknown,
                "priority": "P%d" % priority,
                "reason_code": row.get("reason_code"),
            })
        else:
            auto.append({"record_id": rid,
                         "decision": row.get("decision"),
                         "reason_code": row.get("reason_code"),
                         "confirmation_status": "auto_accepted_below_gate"})

    queue.sort(key=lambda r: (r["priority"], r["record_id"]))
    stats = {
        "total": len(rows),
        "queued": len(queue),
        "auto_accepted": len(auto),
        "by_priority": {p: sum(1 for r in queue if r["priority"] == p)
                        for p in ("P1", "P2", "P3")},
        "by_trigger": {t: sum(1 for r in queue if t in r["queue_reasons"])
                       for t in ("T1", "T2", "T3", "T4", "T5", "T6")},
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump({
            "queue": queue,
            "auto_accepted": auto,
            "stats": stats,
            "contract": "队列内记录的模型判定一律为 pending_human_confirmation；"
                        "禁止把队列内建议当作最终结论交付。",
        }, fh, ensure_ascii=False, indent=2)
    print("TRIAGE queued=%d auto=%d (P1=%d P2=%d P3=%d) -> %s" % (
        stats["queued"], stats["auto_accepted"],
        stats["by_priority"]["P1"], stats["by_priority"]["P2"],
        stats["by_priority"]["P3"], args.out))
    sys.exit(0)


if __name__ == "__main__":
    main()
