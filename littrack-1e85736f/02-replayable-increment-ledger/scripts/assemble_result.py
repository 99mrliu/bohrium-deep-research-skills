#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 把增量记录、回放结论、幂等结论汇入最终 result.json。

- case_id 与 output_contract 字段清单均从 case.json 读取；
- 对 output_contract 中每个字段尽力填充；无法判定的字段填 null 并在
  uncertainty 中显式说明（诚实 partial）；
- 永远附带 sources / uncertainty / change_records。

用法：
  python3 assemble_result.py --case case.json --journal increment_journal.jsonl \
      --run-summary run1.json --run-summary run2.json \
      --replay-diff replay_diff_round2.json --idempotency idem.json \
      --snapshot-prev snapshot_round1.json --snapshot-new snapshot_round2.json \
      --out result.json
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import journal_lib as jl


def load_json(path):
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def event_brief(ev):
    return {
        "dedup_key": ev.get("dedup_key"),
        "title": ev.get("title"),
        "source": ev.get("source"),
        "decision": ev.get("decision"),
        "rule": ev.get("rule"),
        "item_date": ev.get("item_date"),
        "locator": ev.get("locator"),
        "matched": ev.get("matched"),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="组装最终 result.json")
    ap.add_argument("--case", required=True)
    ap.add_argument("--journal", required=True)
    ap.add_argument("--run-summary", action="append", default=[],
                    help="各轮 run summary；最后一个视为本轮")
    ap.add_argument("--replay-diff", action="append", default=[])
    ap.add_argument("--idempotency", default=None)
    ap.add_argument("--snapshot-prev", default=None, help="本轮之前的快照")
    ap.add_argument("--snapshot-new", default=None, help="本轮之后的快照")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    case = load_json(args.case) or {}
    case_id = case.get("case_id")
    contract = case.get("output_contract") or []

    summaries = [load_json(p) for p in args.run_summary]
    summaries = [s for s in summaries if s]
    latest = summaries[-1] if summaries else None
    replay_diffs = [load_json(p) for p in args.replay_diff]
    replay_diffs = [r for r in replay_diffs if r]
    idem = load_json(args.idempotency)
    snap_prev = load_json(args.snapshot_prev)
    snap_new = load_json(args.snapshot_new)

    uncertainty = []
    limitations = []

    # ---- 回放与幂等总体结论 ----
    replay_ok = bool(replay_diffs) and all(r.get("status") == "consistent" for r in replay_diffs)
    idem_ok = bool(idem) and idem.get("status") == "pass"
    if not replay_diffs:
        uncertainty.append("未提供回放报告（replay_diff），无法给出逐字节一致性结论。")
    if not idem:
        uncertainty.append("未提供幂等性校验报告。")
    if not latest:
        uncertainty.append("未提供任何 run summary，本轮增量内容缺失。")

    complete = bool(latest) and (not replay_diffs or replay_ok) and (idem is None or idem_ok)
    status = "complete" if complete else "partial"

    # ---- 本轮清单 ----
    events = (latest or {}).get("events") or []
    new_items = [event_brief(e) for e in events if e.get("decision") == "new"]
    version_updates = [event_brief(e) for e in events if e.get("decision") == "version_update"]
    duplicates = [event_brief(e) for e in events if e.get("decision") == "duplicate"]

    # ---- journal 引用 ----
    journal_ref = {
        "path": args.journal,
        "sha256": jl.sha256_file(args.journal) if os.path.exists(args.journal) else None,
        "record_count": len(jl.read_journal(args.journal)),
        "run_ids": [s.get("run_id") for s in summaries],
    }

    replay_verification = {
        "status": "consistent" if replay_ok and replay_diffs else (
            "not_run" if not replay_diffs else "inconsistent"),
        "byte_equal": replay_ok if replay_diffs else None,
        "runs_replayed": [r.get("run_id") for r in replay_diffs],
        "report_paths": args.replay_diff,
    }
    idempotency_verification = None
    if idem:
        idempotency_verification = {
            "status": idem.get("status"),
            "journal_byte_identical_after_rerun": idem.get("journal_byte_identical_after_rerun"),
            "new_events_after_rerun": idem.get("new_events_after_rerun"),
            "deliveries_after_rerun": idem.get("deliveries_after_rerun"),
            "report_path": args.idempotency,
        }

    # ---- change_records：本轮相对上一快照的全部变更 ----
    change_records = []
    run_id = (latest or {}).get("run_id")
    for e in new_items + version_updates:
        change_records.append({
            "op": "add" if e["decision"] == "new" else "update",
            "field": "seen_items",
            "dedup_key": e["dedup_key"],
            "rule": e["rule"],
            "run_id": run_id,
            "locator": e["locator"],
        })
    wm_before = ((latest or {}).get("watermarks_before")) or (snap_prev or {}).get("sources") or {}
    wm_after = ((latest or {}).get("watermarks_after")) or (snap_new or {}).get("sources") or {}
    for src in sorted(set(wm_before) | set(wm_after)):
        b, a = wm_before.get(src) or {}, wm_after.get(src) or {}
        if jl.canonical_json(b) != jl.canonical_json(a):
            change_records.append({
                "op": "update",
                "field": "sources.%s.watermark" % src,
                "before": b or None,
                "after": a or None,
                "run_id": run_id,
            })
    change_records.append({
        "op": "append",
        "field": "increment_journal",
        "run_id": run_id,
        "journal_line": (latest or {}).get("journal_line"),
        "locator": {"file": args.journal},
    })

    # ---- sources：全部输入材料 + 产物，含 sha256 供复核 ----
    sources = []
    seen_paths = set()

    def add_source(path, role):
        if not path or path in seen_paths or not os.path.exists(path):
            return
        seen_paths.add(path)
        sources.append({"file": path, "role": role, "sha256": jl.sha256_file(path)})

    for s in summaries:
        for src in s.get("sources") or []:
            add_source(src.get("path"), "bibliographic-response/%s" % src.get("name"))
    add_source(args.case, "case-definition")
    add_source(args.snapshot_prev, "previous-snapshot")
    add_source(args.snapshot_new, "new-snapshot")
    add_source(args.journal, "increment-journal")
    for p in args.replay_diff:
        add_source(p, "replay-diff-report")
    add_source(args.idempotency, "idempotency-report")
    for ev in events:
        loc = ev.get("locator") or {}
        for s in sources:
            if s["file"] == loc.get("file"):
                s.setdefault("json_paths_used", [])
                if loc.get("json_path") not in s["json_paths_used"]:
                    s["json_paths_used"].append(loc.get("json_path"))

    # ---- 已知不确定性 ----
    uncertainty.append(
        "标题指纹判重（R4）对极短标题或完全不同表述的同文重复可能误判；"
        "本轮命中的 R4 均有 locator 可人工复核。")
    uncertainty.append(
        "Crossref 日期粒度为日级、arXiv 为秒级；水位比较统一规范化为 UTC 秒级后取 max。")

    known = {
        "case_id": case_id,
        "status": status,
        "window": (latest or {}).get("window"),
        "new_items": new_items,
        "version_updates": version_updates,
        "duplicates": duplicates,
        "deliveries": (latest or {}).get("deliveries") or [],
        "journal_ref": journal_ref,
        "replay_verification": replay_verification,
        "idempotency_verification": idempotency_verification,
        "change_records": change_records,
        "sources": sources,
        "uncertainty": uncertainty,
        "counts": (latest or {}).get("counts"),
        "watermarks": wm_after or None,
        "limitations": limitations,
    }

    result = {}
    if contract:
        for field in contract:
            if field in known:
                result[field] = known[field]
            else:
                result[field] = None
                result.setdefault("uncertainty", list(uncertainty))
                result["uncertainty"].append(
                    "output_contract 字段 %r 无已知映射，填 null。" % field)
    else:
        result = dict(known)
        result["uncertainty"] = uncertainty
        result["uncertainty"].append("case.json 未提供 output_contract，输出全部已知字段。")

    # 契约之外的必备字段兜底
    result.setdefault("case_id", case_id)
    result.setdefault("status", status)
    result.setdefault("sources", sources)
    result.setdefault("uncertainty", uncertainty)
    result.setdefault("change_records", change_records)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, sort_keys=True, indent=2)
        f.write("\n")
    print(json.dumps({"status": status, "case_id": case_id,
                      "out": args.out,
                      "contract_fields": len(contract)}, ensure_ascii=False))
    return 0 if status == "complete" else 2


if __name__ == "__main__":
    sys.exit(main())
