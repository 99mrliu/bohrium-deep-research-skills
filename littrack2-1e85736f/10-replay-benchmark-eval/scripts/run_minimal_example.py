#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_minimal_example.py — 端到端运行 examples/minimal 合成示例并自检。

执行流水线：
  snapshot_align -> truth_build -> metrics -> regression -> report -> assemble_result

自检内容：
  1. 真值分类计数与合成数据埋点一致（new=4, backfill=1, out_of_window=1）；
  2. TP=2 / FP=1 / FN=2 / 重复=1，backfill 误报为 new 被单独标出（=1）；
  3. 指标手算可对上：precision=2/3, recall=1/2, duplicate_rate=1/4, false_alert_rate=1/3；
  4. 回归检测标出 recall_regression（基线 0.75 -> 本次 0.50）；
  5. result.json 含 output_contract 全部字段且 status="ok"；
  6. bundle 约束自查：文件数 ≤50、单文件 ≤500KB、总计 ≤2MB、无符号链接、
     全部 UTF-8 文本可解码、每个文件带扩展名。

任一断言失败即非零退出。仅使用 Python3 标准库，完全离线。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
EX = ROOT / "examples" / "minimal"
MAT = EX / "materials"
OUT = EX / "output"

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024

failures = []


def check(cond, msg):
    print(("PASS" if cond else "FAIL") + "  " + msg)
    if not cond:
        failures.append(msg)


def run_step(script, *args):
    cmd = [sys.executable, str(SCRIPTS / script)] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit("步骤失败: %s" % script)
    print("  $ %s -> %s" % (script, (r.stdout or "").strip()))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    case = json.loads((EX / "case.json").read_text(encoding="utf-8"))
    win = case["window"]

    print("== 端到端流水线 ==")
    run_step("snapshot_align.py", "--prev", MAT / "snapshot_prev.json",
             "--now", MAT / "snapshot_now.json", "--out", OUT / "aligned.json")
    run_step("truth_build.py", "--aligned", OUT / "aligned.json",
             "--window-start", win["start"], "--window-end", win["end"],
             "--out", OUT / "truth.json")
    run_step("metrics.py", "--truth", OUT / "truth.json",
             "--candidates", MAT / "candidate_new_items.json",
             "--aligned", OUT / "aligned.json", "--out", OUT / "metrics.json")
    run_step("regression.py", "--current", OUT / "metrics.json",
             "--history", MAT / "run_history.json", "--out", OUT / "regression.json")
    run_step("report.py", "--truth", OUT / "truth.json", "--metrics", OUT / "metrics.json",
             "--regression", OUT / "regression.json", "--case", EX / "case.json",
             "--out", OUT / "eval_report.md")
    run_step("assemble_result.py", "--case", EX / "case.json", "--truth", OUT / "truth.json",
             "--metrics", OUT / "metrics.json", "--regression", OUT / "regression.json",
             "--report", OUT / "eval_report.md", "--out", OUT / "result.json")

    print("\n== 埋点断言 ==")
    truth = json.loads((OUT / "truth.json").read_text(encoding="utf-8"))
    met = json.loads((OUT / "metrics.json").read_text(encoding="utf-8"))
    reg = json.loads((OUT / "regression.json").read_text(encoding="utf-8"))
    res = json.loads((OUT / "result.json").read_text(encoding="utf-8"))

    tc, c, m = truth["counts"], met["counts"], met["metrics"]
    check(tc["new"] == 4, "真值 truth_new = 4（实际 %d）" % tc["new"])
    check(tc["backfill"] == 1, "真值 truth_backfill = 1（实际 %d）" % tc["backfill"])
    check(tc["out_of_window"] == 1, "真值 truth_out_of_window = 1（实际 %d）" % tc["out_of_window"])

    check(c["tp"] == 2, "TP = 2（实际 %d）" % c["tp"])
    check(c["fp"] == 1, "FP = 1（实际 %d）" % c["fp"])
    check(c["fn"] == 2, "FN = 2（候选漏报 2 条真新增，实际 %d）" % c["fn"])
    check(c["duplicates"] == 1, "重复声明 = 1（实际 %d）" % c["duplicates"])
    check(c["backfill_misreported_as_new"] == 1,
          "backfill 误报为 new 单独计数 = 1（实际 %d）" % c["backfill_misreported_as_new"])
    check(any(x["fp_reason"] == "backfill_misreported_as_new" for x in met["fp_items"]),
          "FP 条目带 fp_reason=backfill_misreported_as_new")

    check(abs(m["precision"] - 2.0 / 3.0) < 1e-6, "precision = 2/3 ≈ 0.6667（实际 %s）" % m["precision"])
    check(abs(m["recall"] - 0.5) < 1e-9, "recall = 0.5（实际 %s）" % m["recall"])
    check(abs(m["duplicate_rate"] - 0.25) < 1e-9, "duplicate_rate = 0.25（实际 %s）" % m["duplicate_rate"])
    check(abs(m["false_alert_rate"] - 1.0 / 3.0) < 1e-6,
          "false_alert_rate = 1/3 ≈ 0.3333（实际 %s）" % m["false_alert_rate"])

    check(reg["status"] == "compared", "回归对比 status=compared")
    flag_types = [f["type"] for f in reg["flags"]]
    check("recall_regression" in flag_types, "标出 recall_regression（0.75 -> 0.50）")
    check(reg["verdict"] == "REGRESSION", "verdict = REGRESSION")

    required = (case.get("output_contract") or {}).get("required_fields") or []
    check(all(k in res for k in required), "result.json 含 output_contract 全部字段")
    check(res["status"] == "ok", "result.json status=ok（实际 %s）" % res["status"])
    check(res["benchmark_constructible"] is True, "benchmark_constructible=true")
    check(res["case_id"] == case["case_id"], "result.json case_id 一致")

    print("\n== bundle 约束自查 ==")
    n_files, total = 0, 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        for name in filenames:
            p = Path(dirpath) / name
            n_files += 1
            check(not p.is_symlink(), "非符号链接: %s" % p.relative_to(ROOT))
            sz = p.stat().st_size
            total += sz
            check(sz <= MAX_FILE_BYTES, "单文件 ≤500KB: %s (%d B)" % (p.relative_to(ROOT), sz))
            check(bool(p.suffix), "文件带扩展名: %s" % p.relative_to(ROOT))
            try:
                p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                check(False, "UTF-8 可解码: %s" % p.relative_to(ROOT))
    check(n_files <= MAX_FILES, "文件总数 ≤50（实际 %d）" % n_files)
    check(total <= MAX_TOTAL_BYTES, "总大小 ≤2MB（实际 %d B）" % total)

    print("\n== 结论 ==")
    if failures:
        print("SELF-CHECK FAILED (%d):" % len(failures))
        for f in failures:
            print("  - " + f)
        return 1
    print("SELF-CHECK PASSED：埋点断言与约束自查全部通过。产物见 %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
