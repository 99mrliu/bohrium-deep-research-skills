#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_minimal_example.py — 一键端到端运行合成示例。

在 bundle 根目录执行：
    python3 scripts/run_minimal_example.py

依次对 examples/minimal/ 运行完整审计链：
    hash_ledger -> validate_schema -> detect_anomalies -> gate -> assemble_result
产物写入 examples/minimal/output/，最后做输出契约自检并打印摘要。
所有步骤仅使用 Python 标准库，完全离线。
"""
import json
import os
import subprocess
import sys

BUNDLE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(BUNDLE_ROOT, "scripts")
EXAMPLE = os.path.join(BUNDLE_ROOT, "examples", "minimal")
MATERIALS = os.path.join(EXAMPLE, "materials")
OUT = os.path.join(EXAMPLE, "output")
CASE_JSON = os.path.join(EXAMPLE, "case.json")
RESULT_JSON = os.path.join(OUT, "result.json")


def run_step(name, argv):
    cmd = [sys.executable, os.path.join(SCRIPTS, name)] + argv
    print("==> %s" % " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.stdout:
        print("    " + proc.stdout.strip().replace("\n", "\n    "))
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit("步骤 %s 失败，退出码 %d" % (name, proc.returncode))


def main():
    with open(CASE_JSON, "r", encoding="utf-8") as fh:
        case = json.load(fh)
    window = case.get("window") or {}
    os.makedirs(OUT, exist_ok=True)

    run_step("hash_ledger.py",
             ["--materials", MATERIALS, "--out",
              os.path.join(OUT, "source_ledger.json")])
    run_step("validate_schema.py",
             ["--materials", MATERIALS, "--out",
              os.path.join(OUT, "schema_report.json")])
    prev = os.path.join(MATERIALS, "previous_snapshot.json")
    run_step("detect_anomalies.py",
             ["--materials", MATERIALS,
              "--window-end", window.get("end"),
              "--window-start", window.get("start"),
              "--previous", prev,
              "--out", os.path.join(OUT, "anomaly_report.json")])
    run_step("gate.py",
             ["--ledger", os.path.join(OUT, "source_ledger.json"),
              "--schema", os.path.join(OUT, "schema_report.json"),
              "--anomalies", os.path.join(OUT, "anomaly_report.json"),
              "--out-dir", OUT])
    run_step("assemble_result.py",
             ["--case", CASE_JSON, "--out-dir", OUT,
              "--result", RESULT_JSON])

    # ---- 输出契约自检 ------------------------------------------------------
    with open(RESULT_JSON, "r", encoding="utf-8") as fh:
        result = json.load(fh)
    contract = case.get("output_contract") or []
    checks = []
    checks.append(("case_id 与 case.json 一致",
                   result.get("case_id") == case.get("case_id")))
    for field in contract:
        checks.append(("contract 字段存在且非 null: %s" % field,
                       field in result and result[field] is not None))
    checks.append(("status == complete", result.get("status") == "complete"))
    checks.append(("sources 非空", bool(result.get("sources"))))
    checks.append(("uncertainty 非空", bool(result.get("uncertainty"))))
    checks.append(("change_records 非空", bool(result.get("change_records"))))

    print("\n---- 自检 ----")
    ok = True
    for label, passed in checks:
        print("[%s] %s" % ("PASS" if passed else "FAIL", label))
        ok = ok and passed

    gating = result.get("gating_decision") or {}
    report = result.get("integrity_report") or {}
    print("\n---- 运行摘要 ----")
    print("case_id        : %s" % result.get("case_id"))
    print("status         : %s" % result.get("status"))
    print("gating         : %s" % gating.get("decision"))
    print("quarantine     : %d 条" % len(result.get("quarantine") or []))
    print("anomaly by_type: %s"
          % json.dumps((report.get("anomaly_summary") or {}).get("by_type"),
                       ensure_ascii=False, sort_keys=True))
    if not ok:
        raise SystemExit("自检未全部通过")
    print("\n全部自检通过，产物位于 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
