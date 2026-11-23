#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_minimal_example.py — 最小示例端到端运行器（一条命令复现）。

从 bundle 根目录或任意目录执行：
    python3 scripts/run_minimal_example.py

流程（对应官方运行时 /input -> /app/work -> /app/output 的分工，
此处 input=examples/minimal，work/output=examples/minimal/output）：
  1. normalize_input.py   语料发现与归一化
  2. verify_evidence.py   严格证据校验（必须零 error 才继续）
  3. build_graph.py       确定性图谱构建（graph.json + graph.jsonl）
  4. query_graph.py       批量执行 case.json 中的 query_specs
  5. assemble_result.py   动态镜像 output_contract，装配全部产物
任一步骤失败即以非零码退出（诚实部分结果由 assemble 阶段负责披露）。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

BUNDLE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = BUNDLE_ROOT / "scripts"
EXAMPLE = BUNDLE_ROOT / "examples" / "minimal"
OUT = EXAMPLE / "output"


def run_step(name, argv):
    print(f"\n=== step: {name} ===")
    proc = subprocess.run([sys.executable] + argv, cwd=str(BUNDLE_ROOT))
    if proc.returncode != 0:
        print(f"!! step {name} 失败，退出码 {proc.returncode}")
        sys.exit(proc.returncode)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # 只清理本流程生成的产物，保持可重入
    for fname in ("normalized_corpus.json", "verify_report.json", "graph.json",
                  "graph.jsonl", "queries.json", "result.json", "ledger.json",
                  "preview.dot", "preview.svg"):
        target = OUT / fname
        if target.exists():
            target.unlink()

    run_step("normalize_input", [
        str(SCRIPTS / "normalize_input.py"),
        "--input", str(EXAMPLE),
        "--out", str(OUT / "normalized_corpus.json"),
    ])
    run_step("verify_evidence", [
        str(SCRIPTS / "verify_evidence.py"),
        "--corpus", str(OUT / "normalized_corpus.json"),
        "--extraction", str(EXAMPLE / "candidate_extraction.json"),
        "--out", str(OUT / "verify_report.json"),
    ])
    run_step("build_graph", [
        str(SCRIPTS / "build_graph.py"),
        "--corpus", str(OUT / "normalized_corpus.json"),
        "--extraction", str(EXAMPLE / "candidate_extraction.json"),
        "--out", str(OUT / "graph.json"),
        "--jsonl", str(OUT / "graph.jsonl"),
    ])
    run_step("query_graph", [
        str(SCRIPTS / "query_graph.py"),
        "--graph", str(OUT / "graph.json"),
        "--batch", str(EXAMPLE / "case.json"),
        "--out", str(OUT / "queries.json"),
    ])
    run_step("assemble_result", [
        str(SCRIPTS / "assemble_result.py"),
        "--case", str(EXAMPLE / "case.json"),
        "--corpus", str(OUT / "normalized_corpus.json"),
        "--graph", str(OUT / "graph.json"),
        "--verify", str(OUT / "verify_report.json"),
        "--queries", str(OUT / "queries.json"),
        "--out-dir", str(OUT),
    ])

    print("\n=== 端到端完成，产物清单 ===")
    total = 0
    for p in sorted(OUT.iterdir()):
        if p.is_file():
            size = p.stat().st_size
            total += size
            print(f"  {p.name:28s} {size:>8d} bytes")
    print(f"  {'TOTAL':28s} {total:>8d} bytes")
    if total > 100 * 1024:
        print("!! 警告：示例输出总量超过 100KB 上限")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
