#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""assemble_result.py — 把各校验产物组装为最终 result.json。

保证：
  * case_id 与 case.json 一致；
  * case.json 的 output_contract 列出的字段全部存在（缺失以 null 补齐，
    并把 status 降级为 partial、在 limitations 中说明）；
  * 必带 sources / uncertainty / change_records；
  * 所有事实性字段值均来自材料或前序脚本产物，脚本自身不编造。

用法：
    python3 assemble_result.py --case case.json --out-dir <校验产物目录> \
        --result <result.json 输出路径>
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

ARTIFACT_NAMES = {
    "source_ledger": "source_ledger.json",
    "schema_report": "schema_report.json",
    "anomaly_report": "anomaly_report.json",
    "integrity_report": "integrity_report.json",
    "quarantine": "quarantine.json",
    "gating_decision": "gating_decision.json",
}


def build_change_records(anomaly_report, ledger_path, ledger):
    """change_records：本次审计发现的'变化'事实——结构漂移、与增量导入
    状态的差异、台账初始化。每条都带 locator 供复核。"""
    records = []
    records.append({
        "change_type": "ledger_initialized",
        "description": "为 %d 个材料文件建立 SHA-256 内容哈希台账（共 %d 字节）"
                       % (ledger.get("total_files", 0),
                          ledger.get("total_bytes", 0)),
        "locator": ledger_path,
        "evidence": None,
    })
    for a in anomaly_report.get("anomalies", []):
        if a.get("type") == "schema_drift":
            records.append({
                "change_type": "schema_drift",
                "description": a.get("detail"),
                "locator": a.get("locator"),
                "evidence": a.get("evidence"),
            })
        elif a.get("type") == "source_record_disappeared":
            records.append({
                "change_type": "source_record_disappeared",
                "description": a.get("detail"),
                "locator": a.get("locator"),
                "evidence": a.get("evidence"),
            })
    prev = anomaly_report.get("previous_snapshot")
    if prev:
        records.append({
            "change_type": "previous_snapshot_comparison",
            "description": (
                "与本地增量导入状态对比：此前导入 %d 条，当前源快照中仍在 %d 条、"
                "消失 %d 条、新增 %s 条"
                % (prev.get("imported_count", 0), prev.get("still_present", 0),
                   prev.get("disappeared_count", 0),
                   str(prev.get("new_record_count")))),
            "locator": prev.get("path"),
            "evidence": prev,
        })
    return records


def build_uncertainties(ledger):
    unc = [
        "固化时间 frozen_at 取自各快照自带字段；离线条件下无法独立验证其真实性，"
        "只能校验其存在性与格式。",
        "本审计校验的是本地固化材料内部的一致性（哈希、Schema、元数据、重复、"
        "漂移）；按离线约束，无法证明上游 API 响应在固化前未被篡改。",
        "重复检测基于规范化 DOI（缺 DOI 时退化为规范化标题）；对跨源重复"
        "（同一论文同时出现在 Crossref 与 Europe PMC）不做合并判定。",
    ]
    for path in ledger.get("ledger_summary_missing_frozen", []) or []:
        unc.append("材料文件 %s 未提供固化时间字段，台账中 frozen_at 为 null。"
                   % path)
    return unc


def main(argv=None):
    parser = argparse.ArgumentParser(description="组装最终 result.json")
    parser.add_argument("--case", required=True, help="case.json 路径")
    parser.add_argument("--out-dir", required=True, help="校验产物所在目录")
    parser.add_argument("--result", required=True, help="result.json 输出路径")
    args = parser.parse_args(argv)

    case = common.load_json(args.case)
    limitations = []
    status = "complete"

    artifacts = {}
    loaded = {}
    for key, fname in ARTIFACT_NAMES.items():
        path = os.path.join(args.out_dir, fname)
        artifacts[key] = path
        if os.path.isfile(path):
            try:
                loaded[key] = common.load_json(path)
            except Exception as exc:
                loaded[key] = None
                limitations.append("产物 %s 无法解析: %s" % (path, exc))
                status = "partial"
        else:
            loaded[key] = None
            limitations.append("产物缺失（对应脚本未成功运行）: %s" % path)
            status = "partial"

    ledger = loaded.get("source_ledger") or {}
    anomaly_report = loaded.get("anomaly_report") or {}
    integrity = loaded.get("integrity_report")
    quarantine = (loaded.get("quarantine") or {}).get("entries", [])
    gating = loaded.get("gating_decision")

    if ledger.get("files"):
        missing_frozen = [f["path"] for f in ledger["files"]
                          if f.get("frozen_at") is None
                          and not f.get("parse_error")]
        ledger["ledger_summary_missing_frozen"] = missing_frozen
        if any(f.get("parse_error") for f in ledger["files"]):
            limitations.append("存在无法解析的源文件，详见 integrity_report."
                               "ledger_summary.parse_errors。")
            status = "partial"

    sources = []
    for f in ledger.get("files", []):
        sources.append({
            "file": f.get("path"),
            "locator": f.get("locator"),
            "sha256": f.get("sha256"),
            "bytes": f.get("bytes"),
            "kind": f.get("kind"),
            "source": f.get("source"),
            "frozen_at": f.get("frozen_at"),
            "frozen_at_locator": f.get("frozen_at_locator"),
            "record_count": f.get("record_count"),
        })

    result = {
        "case_id": case.get("case_id"),
        "status": status,
        "task": case.get("task"),
        "window": case.get("window"),
        "gating_decision": gating,
        "integrity_report": integrity,
        "quarantine": quarantine,
        "sources": sources,
        "uncertainty": build_uncertainties(ledger),
        "change_records": build_change_records(
            anomaly_report, artifacts["source_ledger"], ledger),
        "limitations": limitations,
        "artifacts": artifacts,
    }
    if case.get("synthetic") is not None:
        result["synthetic"] = case.get("synthetic")
    if case.get("synthetic_note"):
        result["synthetic_note"] = case.get("synthetic_note")

    # ---- 输出契约强制检查 ---------------------------------------------------
    contract = case.get("output_contract") or []
    missing = [field for field in contract if field not in result]
    for field in missing:
        result[field] = None
    if missing:
        result["status"] = "partial"
        result["limitations"] = result["limitations"] + [
            "output_contract 要求的字段未能生成，以 null 补齐: %s"
            % ", ".join(missing)]

    if result.get("case_id") is None:
        result["status"] = "partial"
        result["limitations"] = result["limitations"] + [
            "case.json 中缺少 case_id 字段。"]

    common.dump_json(result, args.result)
    print("assemble_result: status=%s, contract 字段 %d 个（缺失 %d 个）-> %s"
          % (result["status"], len(contract), len(missing), args.result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
