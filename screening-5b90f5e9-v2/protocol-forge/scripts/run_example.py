#!/usr/bin/env python3
"""run_example.py -- 检索协议铸造的最小合成示例（端到端）。

在 bundle 根目录执行：  python3 scripts/run_example.py
流程：
  1. build_protocol.py  由 research_question.json 生成三库检索协议；
  2. lint_query.py      对生成的协议过语法门禁（应 PASS）；
  3. lint_query.py      对 examples 中的"历史遗留坏查询"过门禁（应 FAIL，exit 3，
                        用于演示门禁能抓住括号不配平/非法字段标签/悬空运算符）；
  4. map_criteria.py    核验纳入/排除标准与概念块的映射。
所有输入均为合成数据。第 3 步的 FAIL 是演示的一部分，不影响示例成功判定。
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EX = os.path.join(ROOT, "examples", "minimal")
OUT = os.path.join(EX, "output")


def run(cmd):
    print("+", " ".join(os.path.basename(c) if c.endswith(".py") else c for c in cmd))
    return subprocess.run([sys.executable] + cmd).returncode


def main():
    os.makedirs(OUT, exist_ok=True)
    rc = run([os.path.join(HERE, "build_protocol.py"),
              "--question", os.path.join(EX, "research_question.json"),
              "--out", OUT])
    if rc != 0:
        return rc

    rc = run([os.path.join(HERE, "lint_query.py"),
              "--protocol", os.path.join(OUT, "search_protocol.json"),
              "--out", OUT])
    lint_ok = (rc == 0)

    # 负向演示：坏查询必须 FAIL
    bad = '("metformin"[tiab] AND ("prediabetes"[tiab] OR ) AND NOT [xx]'
    rc_bad = run([os.path.join(HERE, "lint_query.py"),
                  "--database", "pubmed", "--query", bad,
                  "--out", os.path.join(OUT, "negative")])
    negative_ok = (rc_bad == 3)
    print("negative-demo: bad query rejected as expected: %s" % negative_ok)

    rc = run([os.path.join(HERE, "map_criteria.py"),
              "--question", os.path.join(EX, "research_question.json"),
              "--criteria", os.path.join(EX, "criteria.json"),
              "--protocol", os.path.join(OUT, "search_protocol.json"),
              "--out", OUT])
    map_ok = (rc == 0)

    ok = lint_ok and negative_ok and map_ok
    print("EXAMPLE %s (lint=%s negative=%s map=%s)"
          % ("PASS" if ok else "FAIL", lint_ok, negative_ok, map_ok))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
