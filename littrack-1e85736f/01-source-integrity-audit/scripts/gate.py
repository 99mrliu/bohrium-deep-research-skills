#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate.py — 汇总校验产物，输出 integrity_report.json / quarantine.json /
gating_decision.json。

gating 规则（详见 references/integrity-rules.md）：
  * block                   ：任一源文件无法解析、题录总数为 0、
                              或 Schema 失败率 > 50%；
  * proceed_with_quarantine ：存在需隔离的题录级异常，但未触及 block 条件；
  * proceed                 ：零异常。

quarantine 清单：凡检出题录级异常（high/medium/low）的记录一律隔离，
隔离动作 = exclude_from_tracking_and_alert_review（不进入后续追踪流水线，
并提示人工复核）；无法解析的文件整文件隔离。

用法：
    python3 gate.py --ledger source_ledger.json --schema schema_report.json \
        --anomalies anomaly_report.json --out-dir <输出目录>
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

BLOCK_FAILURE_RATE = 0.5


def main(argv=None):
    parser = argparse.ArgumentParser(description="汇总校验产物并做出 gating 决策")
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--anomalies", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)

    ledger = common.load_json(args.ledger)
    schema = common.load_json(args.schema)
    anomalies = common.load_json(args.anomalies)

    # ---- 文件级问题 -------------------------------------------------------
    parse_errors = []
    content_duplicates = []
    missing_frozen = []
    for f in ledger.get("files", []):
        if f.get("parse_error"):
            parse_errors.append({"path": f["path"], "locator": f["locator"],
                                 "error": f["parse_error"]})
        if f.get("content_duplicate_of"):
            content_duplicates.append({"path": f["path"],
                                       "duplicate_of": f["content_duplicate_of"]})
        if f.get("frozen_at") is None and not f.get("parse_error"):
            missing_frozen.append(f["path"])

    # ---- quarantine 清单 --------------------------------------------------
    quarantine = []
    for pe in parse_errors:
        quarantine.append({
            "scope": "file",
            "record_locator": None,
            "source_file": pe["path"],
            "locator": pe["locator"],
            "anomaly_types": ["file_unparseable"],
            "severities": ["high"],
            "action": "exclude_from_tracking_and_alert_review",
            "reason": "文件无法解析: %s" % pe["error"],
        })
    by_record = {}
    for a in anomalies.get("anomalies", []):
        rl = a.get("record_locator")
        if not rl:
            continue  # 文件级/快照级异常不进 quarantine（进 integrity_report）
        slot = by_record.setdefault(rl, {"types": [], "severities": [],
                                         "details": []})
        slot["types"].append(a["type"])
        slot["severities"].append(a["severity"])
        slot["details"].append(a["detail"])
    for rl, slot in sorted(by_record.items()):
        quarantine.append({
            "scope": "record",
            "record_locator": rl,
            "source_file": rl.split("#")[0],
            "locator": rl,
            "anomaly_types": slot["types"],
            "severities": sorted(set(slot["severities"])),
            "action": "exclude_from_tracking_and_alert_review",
            "reason": "; ".join(slot["details"]),
        })

    # ---- gating 决策 ------------------------------------------------------
    total_records = schema.get("total_records", 0)
    failure_rate = schema.get("failure_rate", 0.0)
    block_reasons = []
    if parse_errors:
        block_reasons.append("%d 个源文件无法解析" % len(parse_errors))
    if total_records == 0:
        block_reasons.append("题录总数为 0，无可追踪数据")
    if failure_rate > BLOCK_FAILURE_RATE:
        block_reasons.append("Schema 失败率 %.1f%% 超过阈值 %.0f%%"
                             % (failure_rate * 100, BLOCK_FAILURE_RATE * 100))
    if block_reasons:
        decision = "block"
    elif quarantine:
        decision = "proceed_with_quarantine"
    else:
        decision = "proceed"

    gating = {
        "generated_by": "gate.py",
        "decision": decision,
        "block_reasons": block_reasons,
        "quarantine_count": len(quarantine),
        "thresholds": {"block_schema_failure_rate": BLOCK_FAILURE_RATE},
        "rationale": (
            "block=源不可用或失败率过半；proceed_with_quarantine=存在可隔离的"
            "局部异常；proceed=零异常。"
        ),
    }

    by_type = anomalies.get("by_type", {})
    by_severity = anomalies.get("by_severity", {})
    integrity_report = {
        "generated_by": "gate.py",
        "ledger_summary": {
            "total_files": ledger.get("total_files"),
            "total_bytes": ledger.get("total_bytes"),
            "algorithm": ledger.get("algorithm"),
            "files_missing_frozen_at": missing_frozen,
            "parse_errors": parse_errors,
            "content_duplicates": content_duplicates,
        },
        "schema_summary": {
            "total_records": total_records,
            "failed_records": schema.get("failed_records"),
            "failure_rate": failure_rate,
        },
        "metadata_summary": {
            "checked": ["doi", "arxiv_id", "pmid", "date", "title",
                        "retraction/correction markers"],
            "now_reference": anomalies.get("now_reference"),
        },
        "anomaly_summary": {
            "total": anomalies.get("anomaly_count"),
            "by_type": by_type,
            "by_severity": by_severity,
        },
        "anomalies": anomalies.get("anomalies", []),
        "previous_snapshot": anomalies.get("previous_snapshot"),
        "quarantine_count": len(quarantine),
        "gating_decision": decision,
    }

    os.makedirs(args.out_dir, exist_ok=True)
    p_integrity = os.path.join(args.out_dir, "integrity_report.json")
    p_quarantine = os.path.join(args.out_dir, "quarantine.json")
    p_gating = os.path.join(args.out_dir, "gating_decision.json")
    common.dump_json(integrity_report, p_integrity)
    common.dump_json({"generated_by": "gate.py",
                      "quarantine_count": len(quarantine),
                      "entries": quarantine}, p_quarantine)
    common.dump_json(gating, p_gating)
    print("gate: decision=%s, quarantine=%d 条 -> %s"
          % (decision, len(quarantine), args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
