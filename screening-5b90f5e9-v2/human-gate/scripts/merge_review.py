#!/usr/bin/env python3
"""merge_review.py -- 人工复核决定回填、校验与合并。

输入：
  --queue     review_queue.json（triage.py 产物）
  --decisions 原始 decisions.json（自动放行记录的来源）
  --human     human_decisions.csv，列：
              record_id,reviewer_id,final_label,rationale
              final_label ∈ {included, excluded, needs_fulltext}
校验（任一违反即对应行拒绝并入并记入 rejected）：
  V1 record_id 必须在队列中；V2 reviewer_id 非空；
  V3 final_label 合法；V4 final_label 与模型建议不同时 rationale 必填；
  V5 同一 record_id 不可有两条决定。
合并：队列记录取人工 final_label（confirmation_status=human_confirmed /
human_overridden）；队列中无人工决定的记录保持 pending 并列入 unresolved；
自动放行记录原样并入。产物 final_decisions.json + confirmation_ledger.json。
存在 unresolved 或 rejected 时 exit 3（诚实阻断：不得假装人工复核已完成）。
"""
import argparse
import csv
import json
import os
import sys

LEGAL = {"included", "excluded", "needs_fulltext"}


def main():
    ap = argparse.ArgumentParser(description="人工复核回填合并")
    ap.add_argument("--queue", required=True)
    ap.add_argument("--decisions", required=True)
    ap.add_argument("--human", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    for p in (args.queue, args.decisions, args.human):
        if not os.path.isfile(p):
            print("MERGE-ERROR: 文件缺失：%s" % p, file=sys.stderr)
            sys.exit(2)
    queue_payload = json.load(open(args.queue, encoding="utf-8"))
    decisions = {r["record_id"]: r
                 for r in json.load(open(args.decisions, encoding="utf-8"))}
    queue = {r["record_id"]: r for r in queue_payload["queue"]}

    accepted, rejected = {}, []
    seen = set()
    with open(args.human, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        need = {"record_id", "reviewer_id", "final_label", "rationale"}
        if not need.issubset(set(reader.fieldnames or [])):
            print("MERGE-ERROR: CSV 缺列，需要 %s" % sorted(need), file=sys.stderr)
            sys.exit(2)
        for ln, row in enumerate(reader, start=2):
            rid = (row.get("record_id") or "").strip()
            reviewer = (row.get("reviewer_id") or "").strip()
            label = (row.get("final_label") or "").strip()
            rationale = (row.get("rationale") or "").strip()

            def reject(reason):
                rejected.append({"line": ln, "record_id": rid, "reason": reason})

            if rid in seen:
                reject("V5-duplicate-decision")
                continue
            if rid not in queue:
                reject("V1-record-not-in-queue")
                continue
            if not reviewer:
                reject("V2-missing-reviewer")
                continue
            if label not in LEGAL:
                reject("V3-illegal-label: %s" % label)
                continue
            suggestion = queue[rid]["model_suggestion"]
            if label != suggestion and not rationale:
                reject("V4-override-without-rationale")
                continue
            seen.add(rid)
            accepted[rid] = {
                "record_id": rid,
                "final_label": label,
                "reviewer_id": reviewer,
                "rationale": rationale,
                "model_suggestion": suggestion,
                "confirmation_status": "human_confirmed"
                if label == suggestion else "human_overridden",
            }

    unresolved = sorted(set(queue) - set(accepted))
    final = []
    for rid in sorted(set(decisions) | set(accepted)):
        if rid in accepted:
            final.append(accepted[rid])
        elif rid in queue:
            final.append({"record_id": rid,
                          "final_label": None,
                          "confirmation_status": "pending_human_confirmation",
                          "model_suggestion": queue[rid]["model_suggestion"],
                          "queue_reasons": queue[rid]["queue_reasons"]})
        else:
            d = decisions[rid]
            final.append({"record_id": rid,
                          "final_label": d.get("decision"),
                          "reason_code": d.get("reason_code"),
                          "confirmation_status": "auto_accepted_below_gate"})

    n_conf = sum(1 for r in accepted.values()
                 if r["confirmation_status"] == "human_confirmed")
    n_over = sum(1 for r in accepted.values()
                 if r["confirmation_status"] == "human_overridden")
    ledger = {
        "queue_size": len(queue),
        "human_decisions_accepted": len(accepted),
        "confirmed": n_conf,
        "overridden": n_over,
        "override_rate": (n_over / len(accepted)) if accepted else None,
        "unresolved": unresolved,
        "rejected_rows": rejected,
        "honesty_note": "unresolved 非空或 rejected 非空时 exit 3："
                        "人工复核未完成，不得声称 completed。",
    }
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "final_decisions.json"), "w",
              encoding="utf-8") as fh:
        json.dump(final, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "confirmation_ledger.json"), "w",
              encoding="utf-8") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2)
    ok = not unresolved and not rejected
    print("MERGE %s: accepted=%d confirmed=%d overridden=%d unresolved=%d rejected=%d"
          % ("COMPLETE" if ok else "INCOMPLETE",
             len(accepted), n_conf, n_over, len(unresolved), len(rejected)))
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
