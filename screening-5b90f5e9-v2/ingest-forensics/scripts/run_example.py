#!/usr/bin/env python3
"""run_example.py -- 端到端跑通最小合成示例。

在 bundle 根目录执行：  python3 scripts/run_example.py
读取 examples/minimal/exports/ 下三个合成导出文件，产出到 examples/minimal/output/。
示例数据全部为合成数据，不对应任何真实文献检索结果。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXPORTS = os.path.join(ROOT, "examples", "minimal", "exports")
OUT = os.path.join(ROOT, "examples", "minimal", "output")


def run(cmd):
    print("+", " ".join(cmd))
    proc = subprocess.run([sys.executable] + cmd)
    return proc.returncode


def main():
    os.makedirs(OUT, exist_ok=True)
    rc = run([os.path.join(HERE, "sniff_parse.py"),
              "--input-dir", EXPORTS, "--out", OUT])
    if rc != 0:
        print("sniff_parse FAILED rc=%d" % rc)
        return rc
    rc = run([os.path.join(HERE, "ingest_audit.py"),
              "--ingest-dir", OUT, "--out", OUT])
    print("ingest_audit rc=%d (0=PASS)" % rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
