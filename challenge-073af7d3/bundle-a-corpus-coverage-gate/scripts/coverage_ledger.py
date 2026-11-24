#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""coverage_ledger.py — 覆盖度台账（仅标准库，确定性输出）。

用法:
    python3 coverage_ledger.py --work DIR [--inject-ledger FILE]

由 --work/canon.jsonl（配合可选的 ingest_report.json）生成 --work/coverage.json：
    per_year_counts        逐年计数（min..max 之间缺年补 0）
    per_source_file_counts 按来源文件的计数
    records_with_year / records_without_year / year_missing_rate
    right_censoring        右删失评估：末年计数 < 0.4 × 前三个完整年中位数 → 疑似不完整
    exclusion_log          筛选排除日志模板（初始空表，逐条记录排除原因）
    closure                计数闭环 {records_total, kept, duplicates, excluded, closure_ok}
                           闭合法则：records_total == kept + duplicates + excluded

退出码：闭环成立 0，否则 1。
--inject-ledger 仅供负向测试：把给定 JSON 原样写为 coverage.json（模拟台账被篡改），
退出码按注入台账自身 closure 数字能否闭合判定（不信任其 closure_ok 标志）。
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

CENSOR_RULE = ("final year suspected partial if its count < 0.4 * median of the "
               "counts of the previous 3 calendar years (missing years count as 0)")


def load_canon(work):
    canon_path = work / "canon.jsonl"
    if not canon_path.exists():
        print("error: canon.jsonl not found; run ingest_corpus.py first", file=sys.stderr)
        sys.exit(2)
    records = []
    for line in canon_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def closure_ok(cl):
    t = cl.get("records_total")
    return isinstance(t, int) and t == (cl.get("kept") or 0) + \
        (cl.get("duplicates") or 0) + (cl.get("excluded") or 0)


def main():
    ap = argparse.ArgumentParser(description="覆盖度台账生成器（stdlib only）")
    ap.add_argument("--work", required=True)
    ap.add_argument("--inject-ledger", default=None,
                    help="负向测试：用给定 JSON 覆盖生成的 coverage.json")
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    cov_path = work / "coverage.json"

    if args.inject_ledger:
        data = json.loads(Path(args.inject_ledger).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print("error: injected ledger is not a JSON object", file=sys.stderr)
            return 2
        cov_path.write_text(json.dumps(data, ensure_ascii=False, indent=2,
                                       sort_keys=True) + "\n", encoding="utf-8")
        ok = closure_ok(data.get("closure", {}))
        print(json.dumps({"coverage_json": str(cov_path), "injected": True,
                          "closure_ok": ok}, ensure_ascii=False, sort_keys=True))
        return 0 if ok else 1

    records = load_canon(work)
    kept = len(records)

    ingest = {}
    ir_path = work / "ingest_report.json"
    if ir_path.exists():
        try:
            ingest = json.loads(ir_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            ingest = {}

    years_present = sorted({r["year"] for r in records if isinstance(r.get("year"), int)})
    per_year = {}
    if years_present:
        for y in range(years_present[0], years_present[-1] + 1):
            per_year[str(y)] = 0
        for r in records:
            if isinstance(r.get("year"), int):
                per_year[str(r["year"])] += 1

    per_source = {}
    for r in records:
        src = str(r.get("source_file") or "(unknown)")
        per_source[src] = per_source.get(src, 0) + 1

    with_year = sum(1 for r in records if isinstance(r.get("year"), int))
    without_year = kept - with_year
    rate = round(without_year / kept, 4) if kept else 0.0

    # 右删失评估
    censor = {"rule": CENSOR_RULE, "assessment": "no_dated_records",
              "suspected_partial_years": []}
    if years_present:
        final = years_present[-1]
        prev = {str(y): per_year.get(str(y), 0)
                for y in (final - 3, final - 2, final - 1)}
        med = statistics.median(prev.values())
        threshold = round(0.4 * med, 4)
        final_count = per_year.get(str(final), 0)
        suspected = med > 0 and final_count < threshold
        censor = {
            "rule": CENSOR_RULE,
            "final_year": final,
            "final_year_count": final_count,
            "previous_3_years": prev,
            "median_previous_3": med,
            "threshold": threshold,
            "suspected_partial_years": [final] if suspected else [],
            "assessment": ("suspected_partial" if suspected
                           else "insufficient_history" if med == 0 else "ok"),
        }

    closure = {
        "records_total": ingest.get("records_total", kept)
        if isinstance(ingest.get("records_total", kept), int) else kept,
        "kept": kept,
        "duplicates": ingest.get("duplicates_removed", 0)
        if isinstance(ingest.get("duplicates_removed", 0), int) else 0,
        "excluded": 0,
    }
    closure["closure_ok"] = closure_ok(closure)

    coverage = {
        "per_year_counts": per_year,
        "per_source_file_counts": dict(sorted(per_source.items())),
        "records_with_year": with_year,
        "records_without_year": without_year,
        "year_missing_rate": rate,
        "right_censoring": censor,
        "exclusion_log": [],
        "closure": closure,
    }
    cov_path.write_text(json.dumps(coverage, ensure_ascii=False, indent=2,
                                   sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"coverage_json": str(cov_path),
                      "year_missing_rate": rate,
                      "right_censoring": censor.get("assessment"),
                      "closure_ok": closure["closure_ok"]},
                     ensure_ascii=False, sort_keys=True))
    return 0 if closure["closure_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
