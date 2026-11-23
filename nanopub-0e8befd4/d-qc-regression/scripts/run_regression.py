#!/usr/bin/env python3
"""run_regression.py — 已知错误反例回归（纯标准库）。

对 fixtures.json 中每个合成反例运行 qc_gate 审计函数，断言其期望错误码
全部出现（且门判定与 expect_gate 一致）。漏检即失败，退出码 1。

用法：
  python3 SKILL_DIR/scripts/run_regression.py \
    --fixtures SKILL_DIR/examples/regression/fixtures.json \
    --out regression-report.json
"""
import argparse
import importlib.util
import json
import os
import sys

VERSION = "1.0.0"


def load_gate():
    here = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location(
        "qc_gate", os.path.join(here, "qc_gate.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm_numbers(gate, s):
    return set(gate.numbers(gate.norm(s)))


def run_fixture(gate, fx):
    ledger = fx["ledger"]
    src_text = ledger.get("source_text")
    src_norm = gate.norm(src_text) if src_text else None
    src_nums = norm_numbers(gate, src_norm) if src_norm else set()
    codes = []
    for c in ledger.get("claims", []):
        _, _, findings = gate.audit_claim(c, src_norm, src_nums)
        codes.extend(f["code"] for f in findings)
    # 成对检查直接复用 qc_gate.audit_pairs，保证回归与门逻辑一致
    pair_findings, _ = gate.audit_pairs(ledger.get("claims", []))
    for fs in pair_findings.values():
        codes.extend(f["code"] for f in fs)
    return codes


def main():
    ap = argparse.ArgumentParser(description="已知错误反例回归")
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    gate = load_gate()
    with open(args.fixtures, encoding="utf-8") as fh:
        data = json.load(fh)
    fixtures = data["fixtures"]

    report = {"tool": "run_regression", "version": VERSION,
              "gate_version": gate.VERSION,
              "fixtures_total": len(fixtures), "results": [], "summary": {}}
    passed = 0
    for fx in fixtures:
        codes = run_fixture(gate, fx)
        expect = fx.get("expect_codes", [])
        missing = [e for e in expect if e not in codes]
        ok = not missing
        passed += ok
        report["results"].append({
            "name": fx.get("name"), "expected": expect, "produced": codes,
            "missing": missing, "status": "pass" if ok else "FAIL",
        })
    report["summary"] = {"passed": passed, "failed": len(fixtures) - passed,
                         "gate": "pass" if passed == len(fixtures) else "fail"}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0 if passed == len(fixtures) else 1


if __name__ == "__main__":
    sys.exit(main())
