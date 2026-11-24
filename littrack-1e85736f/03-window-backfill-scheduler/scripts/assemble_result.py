#!/usr/bin/env python3
"""assemble_result.py — 组装最终 result.json。

汇总 case_id + output_contract 全部字段 + sources + uncertainty + change_records。
所有字段值均来自案例材料与流水线中间产物（带 locator），不引入任何外部数据。

用法：
  python3 assemble_result.py --case-dir <dir> --work-dir <dir> --out result.json
      [--status complete|partial] [--limitation "额外限制说明，可多次"]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from window_common import dump_json, load_json  # noqa: E402


def item_summary(rec):
    pub, idx = rec.get("published"), rec.get("indexed")
    return {
        "doi": rec.get("doi"),
        "title": rec.get("title"),
        "source": rec.get("source"),
        "content_window": rec.get("content_window"),
        "published_utc": {"earliest": pub["earliest"], "latest": pub["latest"],
                          "precision": pub["precision"]} if pub else None,
        "indexed_utc": idx["earliest"] if idx else None,
        "flags": rec.get("flags", []),
        "note": rec.get("note"),
        "locators": {
            "item": rec.get("item_locator"),
            "published": pub.get("locator") if pub else None,
            "indexed": idx.get("locator") if idx else None,
        },
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="组装 result.json")
    ap.add_argument("--case-dir", required=True)
    ap.add_argument("--case-file", default="case.json")
    ap.add_argument("--work-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--status", default="complete", choices=["complete", "partial"])
    ap.add_argument("--limitation", action="append", default=[])
    args = ap.parse_args(argv)

    case = load_json(os.path.join(args.case_dir, args.case_file))
    plan = load_json(os.path.join(args.work_dir, "window_plan.json"))
    proof = load_json(os.path.join(args.work_dir, "seam_proof.json"))
    assigned = load_json(os.path.join(args.work_dir, "assigned_items.json"))
    backfill = load_json(os.path.join(args.work_dir, "backfill_events.json"))
    normalized = load_json(os.path.join(args.work_dir, "normalized_items.json"))

    items = assigned["items"]
    current_additions = [item_summary(r) for r in items
                         if r["classification"] in ("current_addition", "low_precision")]
    deferred = [item_summary(r) for r in items if r["classification"] == "deferred"]
    undated = []
    for r in items:
        if r["classification"] != "undated":
            continue
        undated.append({
            "doi": r.get("doi"),
            "title": r.get("title"),
            "source": r.get("source"),
            "reason": r.get("reason"),
            "honest_note": "无法从源记录确定 published 日期，不做猜测，进入 undated 清单",
            "unparseable_published": r.get("unparseable_published"),
            "locator": r.get("item_locator"),
        })

    uncertainty = []
    for r in items:
        if "low_precision_date" in r.get("flags", []):
            uncertainty.append(
                "条目 %s 的 published 精度为 %s（区间 [%s, %s]），内容窗口无法唯一确定，"
                "已按 low_precision 计入本轮新增并标记"
                % (r.get("doi"), r["published"]["precision"],
                   r["published"]["earliest"], r["published"]["latest"]))
        if r.get("published") and r["published"].get("assumed_timezone"):
            uncertainty.append(
                "条目 %s 的 published 时间戳无时区标记，已假定为 UTC"
                % r.get("doi"))
        if "no_indexed_date_assumed_current_round" in r.get("flags", []):
            uncertainty.append(
                "条目 %s 缺少 indexed 时间，按本轮新到处理" % r.get("doi"))
    if not proof.get("overall_pass"):
        uncertainty.append("seam_proof 未全部通过，窗口链存在断裂接缝")
    uncertainty.extend(args.limitation)

    materials = normalized.get("materials", [])
    per_source = {}
    for it in normalized.get("items", []):
        per_source[it["source_file"]] = per_source.get(it["source_file"], 0) + 1
    sources = [
        {"file": m, "role": "source_bibliographic_snapshot",
         "item_count": per_source.get(m, 0)}
        for m in materials
    ]
    snap = case.get("previous_snapshot")
    if snap:
        sources.append({"file": snap, "role": "previous_window_state_snapshot"})
    sources.append({"file": args.case_file, "role": "case_definition"})

    counts = assigned.get("counts", {})
    change_records = [
        {"step": 1, "script": "window_planner.py", "output": "window_plan.json",
         "detail": "从 previous_snapshot 终点接续生成窗口链：current=%s"
                   % ",".join(plan.get("current_window_ids", []))},
        {"step": 2, "script": "seam_proof.py", "output": "seam_proof.json",
         "detail": "逐接缝证明 %d 条，overall_pass=%s"
                   % (len(proof.get("seams", [])), proof.get("overall_pass"))},
        {"step": 3, "script": "date_normalize.py", "output": "normalized_items.json",
         "detail": "归一化 %d 条题录的 published/indexed 日期为 UTC 区间"
                   % normalized.get("item_count", 0)},
        {"step": 4, "script": "assign_windows.py", "output": "assigned_items.json",
         "detail": "归属判定计数：%s" % counts},
        {"step": 5, "script": "backfill.py", "output": "backfill_events.json",
         "detail": "生成 %d 条延迟入库补抓事件" % backfill.get("backfill_count", 0)},
        {"step": 6, "script": "assemble_result.py", "output": "result.json",
         "detail": "汇总 output_contract 字段 + sources + uncertainty + change_records"},
    ]

    status = args.status
    if not proof.get("overall_pass") and status == "complete":
        status = "partial"
        uncertainty.append("因 seam_proof 未通过，状态自动降级为 partial")

    result = {
        "case_id": case.get("case_id"),
        "status": status,
        "window_plan": plan,
        "seam_proof": proof,
        "current_window_additions": current_additions,
        "backfill_events": backfill["events"],
        "deferred_items": deferred,
        "undated_items": undated,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
    }
    # 对照 output_contract 检查字段齐全（缺失则诚实标 partial）
    contract = case.get("output_contract") or []
    missing = [f for f in contract if f not in result]
    if missing:
        result["status"] = "partial"
        result["uncertainty"].append("output_contract 字段缺失：%s" % ", ".join(missing))
    result["output_contract_check"] = {
        "contract": contract,
        "missing_fields": missing,
        "all_present": not missing,
    }
    dump_json(result, args.out)
    print("result -> %s | status=%s additions=%d backfill=%d deferred=%d undated=%d"
          % (args.out, result["status"], len(current_additions),
             len(backfill["events"]), len(deferred), len(undated)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
