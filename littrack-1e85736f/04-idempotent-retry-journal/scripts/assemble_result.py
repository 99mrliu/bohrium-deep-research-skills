#!/usr/bin/env python3
"""assemble_result.py — 组装 result.json（离线，仅标准库）。

从 checkpoint.json / retry_journal.jsonl / delivery_log.jsonl / runs.jsonl
组装最终交付，逐字段对照 case.json 的 output_contract：
  - 全部源完成且无降级  -> status = "ok"
  - 存在降级/阻断/未完成 -> status = "partial"，degraded_sources 说明原因，
    uncertainty 明确缺失覆盖
  - items 全部来自 delivery_log（每条带 locator：文件 + JSON 路径）
  - change_records 来自 runs.jsonl + journal 终止性事件

CLI:
  python3 assemble_result.py --case /path/case.json --work /app/work \
      --out /app/output/result.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import checkpoint as ck
import delivery_dedup as dd

TERMINAL_EVENTS = ("success", "degrade_source", "block_source")


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def assemble(case_path, work_dir, out_path):
    with open(case_path, "r", encoding="utf-8") as f:
        case = json.load(f)
    case_id = case["case_id"]
    default_window = case.get("window", {}).get("id", "default")

    cp = ck.load(os.path.join(work_dir, "checkpoint.json"), case_id=case_id)
    journal = read_jsonl(os.path.join(work_dir, "retry_journal.jsonl"))
    deliveries = dd.read_all(os.path.join(work_dir, "delivery_log.jsonl"))
    runs = read_jsonl(os.path.join(work_dir, "runs.jsonl"))

    # items：全部来自投递账本，带 locator 供复核
    items = [{"doi": d.get("doi"), "title": d.get("title"),
              "source": d.get("source"), "window": d.get("window"),
              "locator": d.get("locator"), "extra": d.get("extra", {})}
             for d in deliveries]

    # degraded_sources：降级源清单与原因
    degraded_sources = []
    for key, info in sorted(cp["degraded"].items()):
        sid, window = key.split("|", 1)
        degraded_sources.append({
            "source": sid, "window": window,
            "failure_class": info["failure_class"],
            "reason": info["reason"], "attempts": info["attempts"],
        })

    # sources：逐源状态
    sources = []
    uncertainty = []
    for src in case.get("sources", []):
        sid = src["source_id"]
        for window in src.get("windows", [default_window]):
            key = ck.make_key(sid, window)
            attempts = sum(1 for e in journal
                           if e.get("source") == sid
                           and e.get("window") == window
                           and e.get("event") == "attempt")
            entry = {"source": sid, "window": window,
                     "material": src["material"], "attempts": attempts}
            if key in cp["completed"]:
                info = cp["completed"][key]
                entry["status"] = "done"
                entry["note"] = info["note"]
                entry["delivered"] = info["delivered"]
                if info["note"] == "empty_window":
                    uncertainty.append(
                        "源 %s 窗口 %s 为空窗口（0 条），非故障。"
                        % (sid, window))
                for rs in info.get("records_skipped", []):
                    uncertainty.append(
                        "源 %s 记录 %s 缺字段 %s，已按 missing_field 策略"
                        "跳过（覆盖不完整）。" % (sid, rs["locator"],
                                                  ",".join(rs["missing"])))
            elif key in cp["degraded"]:
                info = cp["degraded"][key]
                entry["status"] = "degraded"
                entry["failure_class"] = info["failure_class"]
                entry["reason"] = info["reason"]
                uncertainty.append(
                    "源 %s 窗口 %s 未覆盖：%s（%s）。"
                    % (sid, window, info["failure_class"], info["reason"]))
            else:
                entry["status"] = "pending"
                uncertainty.append("源 %s 窗口 %s 尚未处理。" % (sid, window))
            sources.append(entry)

    all_keys = [ck.make_key(s["source_id"], w)
                for s in case.get("sources", [])
                for w in s.get("windows", [default_window])]
    incomplete = [k for k in all_keys if k not in cp["completed"]]
    status = "ok" if not incomplete and not cp["degraded"] else "partial"

    # change_records：每轮运行摘要 + 终止性决策事件
    change_records = []
    for r in runs:
        change_records.append({
            "run_no": r["run_no"], "event": "run_summary",
            "detail": ("processed=%d skipped_completed=%d degraded=%d "
                       "delivered=%d dedup_skipped=%d records_skipped=%d"
                       % (r["processed"], r["skipped_completed"],
                          r["degraded"], r["delivered"],
                          r["dedup_skipped"], r["records_skipped"])),
            "ts": r["ts_end"]})
    for e in journal:
        dec = e.get("decision", "")
        if any(dec.startswith(t) for t in TERMINAL_EVENTS) and dec != "success":
            change_records.append({
                "run_no": e["run_no"], "event": "terminal_decision",
                "detail": "%s|%s attempt %d: %s -> %s" % (
                    e["source"], e["window"], e["attempt_no"],
                    e["failure_class"], dec),
                "ts": e["ts"]})
    change_records.sort(key=lambda x: (x.get("ts") or "", x.get("run_no") or 0))

    result = {
        "case_id": case_id,
        "status": status,
        "window": case.get("window"),
        "items": items,
        "degraded_sources": degraded_sources,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "stats": {
            "runs": len(runs),
            "items_delivered": len(deliveries),
            "sources_done": len(cp["completed"]),
            "sources_degraded": len(cp["degraded"]),
        },
    }

    # output_contract 逐字段兜底：缺字段置 None 并写入 uncertainty
    for field in case.get("output_contract", []):
        if field not in result:
            result[field] = None
            result["uncertainty"].append(
                "output_contract 字段 %r 本流水线未产出，置 null。" % field)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    tmp = out_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, out_path)
    return result


def main(argv):
    ap = argparse.ArgumentParser(description="assemble result.json (offline)")
    ap.add_argument("--case", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv[1:])
    result = assemble(args.case, args.work, args.out)
    print("wrote %s (status=%s, items=%d, degraded=%d)"
          % (args.out, result["status"], len(result["items"]),
             len(result["degraded_sources"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
