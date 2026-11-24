#!/usr/bin/env python3
"""run_example.py -- 人工确认门禁的最小合成示例（端到端）。

在 bundle 根目录执行：  python3 scripts/run_example.py
流程（全部合成数据）：
  1. triage.py       10 条合成判定 → 6 条入队（T1–T6 全覆盖）、4 条自动放行；
  2. merge_review.py 用完整人工决定表回填 → COMPLETE，exit 0；
  3. merge_review.py 用残缺人工决定表回填（一行推翻无理由、一行不在队列、
                     一条队列记录未决定）→ INCOMPLETE，exit 3（预期演示）。
产物写 examples/minimal/output/。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, "examples", "minimal")
OUT = os.path.join(EX, "output")


def run(cmd, expect=0):
    rc = subprocess.run([sys.executable] + cmd).returncode
    ok = rc == expect
    print("  rc=%d expected=%d %s" % (rc, expect, "OK" if ok else "MISMATCH"))
    return ok


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    ok = True

    print("[1] triage")
    ok &= run([os.path.join(HERE, "triage.py"),
               "--decisions", os.path.join(EX, "decisions.json"),
               "--out", os.path.join(OUT, "review_queue.json")])

    print("[2] merge complete -> 应 exit 0")
    ok &= run([os.path.join(HERE, "merge_review.py"),
               "--queue", os.path.join(OUT, "review_queue.json"),
               "--decisions", os.path.join(EX, "decisions.json"),
               "--human", os.path.join(EX, "human_decisions_complete.csv"),
               "--out", os.path.join(OUT, "complete")], expect=0)

    print("[3] merge partial -> 应 INCOMPLETE exit 3")
    ok &= run([os.path.join(HERE, "merge_review.py"),
               "--queue", os.path.join(OUT, "review_queue.json"),
               "--decisions", os.path.join(EX, "decisions.json"),
               "--human", os.path.join(EX, "human_decisions_partial.csv"),
               "--out", os.path.join(OUT, "partial")], expect=3)

    print("EXAMPLE %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
