#!/usr/bin/env python3
"""fill_example_plan.py — 合成示例的 plan 自动补全器（合成示例专用）。

真实运行时由 Agent 编辑 slide_plan.json；本脚本仅在 examples/run_example.sh 中
代替 Agent 完成这一步，使示例可以非交互跑通。只基于 S2/S4 已抽取的候选内容
（逐字行 + 图候选）润色 claim/notes/mainline，不引入任何源文之外的数字。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stage_machine import now_iso, read_json, write_json

TITLES = {
    "title": None,  # 保留论文标题
    "background": "Background: Long-Context Protein Modeling",
    "method": "Method: Adaptive Sparse Attention",
    "results": "Results: Accuracy and Latency Gains",
    "discussion": "Discussion: Transfer and Limitations",
    "conclusion": "Conclusion: Practical Long-Context Protein LMs",
}
CLAIMS = {
    "title": "SparProtein：面向长上下文蛋白语言模型的自适应稀疏注意力",
    "background": "长序列蛋白建模受注意力平方复杂度制约",
    "method": "自适应稀疏注意力在保精度的同时降低推理成本",
    "results": "SparProtein 精度更高且推理延迟显著下降",
    "discussion": "稀疏模式可迁移，但在短序列上收益收窄",
    "conclusion": "自适应稀疏是长上下文蛋白建模的实用路线",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True, help="prepare 阶段使用的工作目录")
    args = ap.parse_args(argv)
    plan_path = os.path.join(os.path.abspath(args.work), "slide_plan.json")
    plan = read_json(plan_path)
    if not plan:
        print(f"ERROR: {plan_path} 不存在或非法，请先运行 prepare", file=sys.stderr)
        return 1

    for s in plan.get("slides", []):
        kind = s.get("kind")
        if TITLES.get(kind):
            s["title"] = TITLES[kind]
        s["claim"] = CLAIMS.get(kind, s.get("claim", ""))
        refs = ", ".join(str(ev.get("ref")) for ev in s.get("evidence", []) if ev.get("ref"))
        first = (s.get("bullets") or [s.get("title", "")])[0]
        s["notes"] = (f"讲稿（约2分钟）：{s['claim']}。要点：{first[:120]}。"
                      f"证据定位：{refs}。（合成示例自动生成的讲稿草稿）")

    slides_by_kind = {s.get("kind"): s for s in plan.get("slides", [])}
    plan["mainline"] = {
        "problem": (slides_by_kind.get("background", {}).get("bullets") or [""])[0][:200],
        "method": (slides_by_kind.get("method", {}).get("bullets") or [""])[0][:200],
        "results": (slides_by_kind.get("results", {}).get("bullets") or [""])[0][:200],
        "limitations": (slides_by_kind.get("discussion", {}).get("bullets") or [""])[0][:200],
    }
    plan["audience"] = "计算生物学方向学术同行（合成示例设定）"
    plan["duration_min"] = 12
    plan.setdefault("meta", {})["filled_by"] = f"fill_example_plan.py (synthetic demo) at {now_iso()}"
    write_json(plan_path, plan)
    print(f"plan filled (synthetic demo): {plan_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
