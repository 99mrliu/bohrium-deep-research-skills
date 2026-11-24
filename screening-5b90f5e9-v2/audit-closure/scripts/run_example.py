#!/usr/bin/env python3
"""run_example.py -- 审计闭合技能的最小合成示例（端到端）。

在 bundle 根目录执行：  python3 scripts/run_example.py
演示四件事（全部合成数据）：
  1. 正确台账 → validate PASS；篡改一条计数 → validate FAIL exit 3（临时副本）；
  2. manifest create/verify → PASS；篡改产物 → verify FAIL exit 3（临时副本）；
  3. rerun_diff：run_a vs run_b（有一处标签翻转）→ NONDETERMINISTIC exit 3（预期）；
  4. rerun_diff：run_a vs run_b_fixed（同内容乱序）→ DETERMINISTIC exit 0。
产物写 examples/minimal/output/。第 1b/2b/3 步的 FAIL 是演示的一部分。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, "examples", "minimal")
OUT = os.path.join(EX, "output")
LEDGER = os.path.join(OUT, "audit_ledger.json")

TS = "2026-11-24T00:00:00Z"


def run(cmd, expect=None):
    rc = subprocess.run([sys.executable] + cmd).returncode
    ok = (expect is None and rc == 0) or (rc == expect)
    print("  rc=%d expected=%s %s" % (rc, expect, "OK" if ok else "MISMATCH"))
    return ok


def record(stage, inc, outc, notes=""):
    return run([os.path.join(HERE, "stage_ledger.py"), "--ledger", LEDGER,
                "record", "--stage", stage,
                "--input-count", str(inc), "--output-count", str(outc),
                "--operator", "example-driver", "--basis", "examples/minimal",
                "--notes", notes, "--timestamp", TS])


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    ok = True

    print("[1] 正确台账（identified 200 → 去重 23 → screened 177 → 12+160+5）")
    ok &= record("identified", 200, 200, "两个库导出合计")
    ok &= record("dedup", 200, 177, "精确重复合并 23 条")
    ok &= record("screened", 177, 177, "全量标题摘要筛选")
    ok &= record("included", 177, 12)
    ok &= record("excluded", 177, 160)
    ok &= record("needs_human", 177, 5)
    ok &= run([os.path.join(HERE, "stage_ledger.py"), "--ledger", LEDGER,
               "validate", "--out", os.path.join(OUT, "closure_report.json")])

    print("[1b] 篡改台账（excluded 160→159）→ 应 FAIL exit 3")
    tmp = tempfile.mkdtemp()
    bad_ledger = json.load(open(LEDGER, encoding="utf-8"))
    for e in bad_ledger["entries"]:
        if e["stage"] == "excluded":
            e["output_count"] = 159
    bad_path = os.path.join(tmp, "bad_ledger.json")
    json.dump(bad_ledger, open(bad_path, "w"), ensure_ascii=False)
    ok &= run([os.path.join(HERE, "stage_ledger.py"), "--ledger", bad_path,
               "validate", "--out", os.path.join(tmp, "bad_report.json")], expect=3)
    shutil.rmtree(tmp)

    print("[2] manifest create/verify")
    ok &= run([os.path.join(HERE, "manifest.py"), "--dir", OUT, "create"])
    ok &= run([os.path.join(HERE, "manifest.py"), "--dir", OUT, "verify"])

    print("[2b] 篡改产物后 verify → 应 FAIL exit 3（临时副本）")
    tmp = tempfile.mkdtemp()
    shutil.copytree(OUT, os.path.join(tmp, "cp"), dirs_exist_ok=True)
    with open(os.path.join(tmp, "cp", "audit_ledger.json"), "a", encoding="utf-8") as fh:
        fh.write(" ")
    ok &= run([os.path.join(HERE, "manifest.py"), "--dir",
               os.path.join(tmp, "cp"), "verify"], expect=3)
    shutil.rmtree(tmp)

    print("[3] rerun_diff run_a vs run_b（一处翻转）→ 应 NONDETERMINISTIC exit 3")
    ok &= run([os.path.join(HERE, "rerun_diff.py"),
               "--a", os.path.join(EX, "decisions_run_a.json"),
               "--b", os.path.join(EX, "decisions_run_b.json"),
               "--out", os.path.join(OUT, "rerun_report_ab.json")], expect=3)

    print("[4] rerun_diff run_a vs run_b_fixed（同内容乱序）→ 应 DETERMINISTIC")
    ok &= run([os.path.join(HERE, "rerun_diff.py"),
               "--a", os.path.join(EX, "decisions_run_a.json"),
               "--b", os.path.join(EX, "decisions_run_b_fixed.json"),
               "--out", os.path.join(OUT, "rerun_report_fixed.json")])

    # manifest 重固化，把 rerun 报告纳入
    ok &= run([os.path.join(HERE, "manifest.py"), "--dir", OUT, "create"])

    print("EXAMPLE %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
