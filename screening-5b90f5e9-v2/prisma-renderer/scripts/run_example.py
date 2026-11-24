#!/usr/bin/env python3
"""run_example.py -- 交付渲染技能的最小合成示例（端到端）。

在 bundle 根目录执行：  python3 scripts/run_example.py
流程（全部合成数据）：
  1. render_flow.py   闭合计数 → flow.svg + flow.md + render_check.json（PASS）；
  2. render_flow.py   篡改计数（excluded 159）→ 应 BLOCKED exit 3（临时文件）；
  3. build_report.py  全量输入 → screening_report.md（无缺失）；
  4. build_report.py  仅 counts → screening_report_partial.md（缺失清单）。
产物写 examples/minimal/output/。flow.svg 为运行时产物；随包保留
flow.md/screening_report*.md/render_check.json 作为文本示意输出。
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


def run(cmd, expect=0):
    rc = subprocess.run([sys.executable] + cmd).returncode
    ok = rc == expect
    print("  rc=%d expected=%d %s" % (rc, expect, "OK" if ok else "MISMATCH"))
    return ok


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    ok = True

    print("[1] render_flow 闭合计数")
    ok &= run([os.path.join(HERE, "render_flow.py"),
               "--counts", os.path.join(EX, "counts.json"),
               "--out", OUT])

    print("[2] render_flow 篡改计数 -> 应 BLOCKED exit 3")
    tmp = tempfile.mkdtemp()
    bad = json.load(open(os.path.join(EX, "counts.json"), encoding="utf-8"))
    bad["excluded"] = 159
    bad_path = os.path.join(tmp, "bad_counts.json")
    json.dump(bad, open(bad_path, "w"), ensure_ascii=False)
    ok &= run([os.path.join(HERE, "render_flow.py"),
               "--counts", bad_path, "--out", os.path.join(tmp, "badout")],
              expect=3)
    shutil.rmtree(tmp)

    print("[3] build_report 全量输入")
    ok &= run([os.path.join(HERE, "build_report.py"),
               "--counts", os.path.join(EX, "counts.json"),
               "--protocol", os.path.join(EX, "protocol_meta.json"),
               "--decisions", os.path.join(EX, "decisions_summary.json"),
               "--flow-md", os.path.join(OUT, "flow.md"),
               "--out", OUT])

    print("[4] build_report 仅 counts（降级）")
    ok &= run([os.path.join(HERE, "build_report.py"),
               "--counts", os.path.join(EX, "counts.json"),
               "--out", os.path.join(OUT, "partial"),
               "--title", "系统性文献筛选报告（降级示例）"])

    print("EXAMPLE %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
