#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_check.py — 语料审计门禁（仅标准库，确定性输出）。

用法:
    python3 gate_check.py --work DIR

检查项:
  (a) canon.jsonl 存在，且每条记录具备非空 id 与 date_provenance（年份溯源）；
  (b) ingest_report 闭环自洽：records_total == records_kept + duplicates_removed，
      且 duplicates_removed 与 duplicates.json 的 pairs 数一致，
      且 records_kept 与 canon.jsonl 行数一致；
  (c) coverage.json 闭环成立：重新计算 records_total == kept + duplicates + excluded
      （不信任文件内的 closure_ok 标志，防篡改），并与 canon/ingest_report 交叉核对；
  (d) year_missing_rate <= 0.2，否则 verdict=warn（不判 fail）；
  (e) canon 中不得存在重复 id，否则 fail。

输出：stdout 与 --work/gate_verdict.json，格式 {gate, violations, warnings, checks}。
退出码：fail → 1；pass / warn → 0。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WARN_YEAR_MISSING_RATE = 0.2


def main():
    ap = argparse.ArgumentParser(description="语料审计门禁（stdlib only）")
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    work = Path(args.work)

    violations, warnings, checks = [], [], {}

    # ---- (a) canon.jsonl 存在性与字段完整性 --------------------------------
    canon_path = work / "canon.jsonl"
    canon = []
    canon_exists = canon_path.exists()
    checks["a_canon_exists"] = canon_exists
    if not canon_exists:
        violations.append("canon_missing: canon.jsonl 不存在，请先运行 ingest_corpus.py")
    else:
        for ln, line in enumerate(canon_path.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                canon.append(json.loads(line))
            except json.JSONDecodeError as e:
                violations.append(f"canon_line_{ln}_invalid_json: {e}")
        bad = [str(r.get("id") or f"line{i}")
               for i, r in enumerate(canon, 1)
               if not (isinstance(r.get("id"), str) and r.get("id"))
               or not r.get("date_provenance")]
        checks["a_records_total"] = len(canon)
        checks["a_records_missing_id_or_provenance"] = len(bad)
        if bad:
            violations.append(
                "canon_missing_id_or_date_provenance: " + ",".join(bad[:10]))

    # ---- (e) canon 内重复 id -------------------------------------------------
    if canon_exists:
        seen, dup_ids = set(), set()
        for r in canon:
            rid = r.get("id")
            if rid in seen:
                dup_ids.add(str(rid))
            seen.add(rid)
        checks["e_duplicate_ids_in_canon"] = sorted(dup_ids)
        if dup_ids:
            violations.append("duplicate_ids_in_canon: " + ",".join(sorted(dup_ids)))

    # ---- (b) ingest_report 闭环与 duplicates.json 一致性 ---------------------
    ingest = None
    ir_path = work / "ingest_report.json"
    if not ir_path.exists():
        violations.append("ingest_report_missing: 请先运行 ingest_corpus.py")
    else:
        try:
            ingest = json.loads(ir_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            violations.append(f"ingest_report_invalid_json: {e}")
            ingest = None
    if ingest is not None:
        t = ingest.get("records_total")
        k = ingest.get("records_kept")
        d = ingest.get("duplicates_removed")
        closed = all(isinstance(x, int) for x in (t, k, d)) and t == k + d
        checks["b_ingest_closure"] = closed
        if not closed:
            violations.append(
                f"ingest_closure_mismatch: records_total({t}) != "
                f"records_kept({k}) + duplicates_removed({d})")
        dup_path = work / "duplicates.json"
        if dup_path.exists():
            try:
                pairs = json.loads(dup_path.read_text(encoding="utf-8")).get("pairs", [])
            except json.JSONDecodeError as e:
                pairs = None
                violations.append(f"duplicates_json_invalid: {e}")
            if pairs is not None:
                checks["b_duplicates_pairs"] = len(pairs)
                if isinstance(d, int) and d != len(pairs):
                    violations.append(
                        f"duplicates_count_mismatch: report={d} pairs={len(pairs)}")
        elif isinstance(d, int) and d > 0:
            violations.append("duplicates_json_missing: 报告声称有重复但文件缺失")
        if canon_exists and isinstance(k, int) and k != len(canon):
            violations.append(
                f"canon_kept_mismatch: records_kept={k} != canon 行数={len(canon)}")

    # ---- (c) coverage.json 闭环（重算，不信任 closure_ok 标志） ---------------
    cov = None
    cov_path = work / "coverage.json"
    if not cov_path.exists():
        violations.append("coverage_missing: 请先运行 coverage_ledger.py")
    else:
        try:
            cov = json.loads(cov_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            violations.append(f"coverage_invalid_json: {e}")
            cov = None
    if cov is not None:
        cl = cov.get("closure") or {}
        ct, ck = cl.get("records_total"), cl.get("kept")
        cd, ce = cl.get("duplicates"), cl.get("excluded")
        equation = isinstance(ct, int) and ct == (ck or 0) + (cd or 0) + (ce or 0)
        checks["c_coverage_closure_equation"] = equation
        checks["c_coverage_closure_flag"] = cl.get("closure_ok")
        if not equation:
            violations.append(
                f"coverage_closure_mismatch: records_total({ct}) != "
                f"kept({ck}) + duplicates({cd}) + excluded({ce})")
        if cl.get("closure_ok") is not True:
            violations.append("coverage_closure_flag_false: closure_ok 不为 true")
        if canon_exists and isinstance(ck, int) and ck != len(canon):
            violations.append(
                f"coverage_kept_mismatch: closure.kept={ck} != canon 行数={len(canon)}")
        if ingest is not None:
            if ct != ingest.get("records_total"):
                violations.append(
                    "coverage_total_mismatch: closure.records_total != "
                    "ingest_report.records_total")
            if cd != ingest.get("duplicates_removed"):
                violations.append(
                    "coverage_duplicates_mismatch: closure.duplicates != "
                    "ingest_report.duplicates_removed")

    # ---- (d) 年份缺失率（超标仅 warn） ---------------------------------------
    if cov is not None:
        rate = cov.get("year_missing_rate")
        if isinstance(rate, (int, float)) and not isinstance(rate, bool):
            checks["d_year_missing_rate"] = rate
            if rate > WARN_YEAR_MISSING_RATE:
                warnings.append(
                    f"year_missing_rate_high: {rate} > {WARN_YEAR_MISSING_RATE}"
                    "；年份缺失过多，趋势结论须显式声明该限制（warn，不判 fail）")

    gate = "fail" if violations else ("warn" if warnings else "pass")
    verdict = {"gate": gate, "violations": violations,
               "warnings": warnings, "checks": checks}
    text = json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        work.mkdir(parents=True, exist_ok=True)
        (work / "gate_verdict.json").write_text(text, encoding="utf-8")
    except OSError:
        pass
    sys.stdout.write(text)
    return 1 if gate == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
