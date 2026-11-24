#!/usr/bin/env python3
"""Auto-complete slide_plan.json for the SYNTHETIC example case only.

This stands in for the agent's creative step in examples/run_example.sh
so the example can run non-interactively. It reads the extracted paper
text and the template inventory, and writes a plan whose layout names are
guaranteed legal (subset of the inventory).

Usage:
    python3 fill_example_plan.py --work /app/work
"""
import argparse
import json
import os
import re
import sys


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--work", required=True)
    args = ap.parse_args(argv)

    inv = load_json(os.path.join(args.work, "template_inventory.json"))
    legal = [l["name"] for l in inv.get("layouts", [])]

    def pick(*preferred):
        for p in preferred:
            if p in legal:
                return p
        return legal[0] if legal else None

    title_layout = pick("Title Slide", "Title Only")
    body_layout = pick("Title and Content", "Title Only")

    text_dir = os.path.join(args.work, "paper", "text")
    pages = {}
    if os.path.isdir(text_dir):
        for fn in os.listdir(text_dir):
            m = re.match(r"page-(\d+)\.txt$", fn)
            if m:
                with open(os.path.join(text_dir, fn), encoding="utf-8") as f:
                    pages[int(m.group(1))] = f.read()
    figs = os.path.join(args.work, "paper", "figs")

    plan = {
        "mainline": {
            "problem": "均匀网格求解浅水方程成本高（p.1 摘要）",
            "method": "基于误差指示子阈值的四叉树自适应加密，二阶有限体积"
                      " + 显式 RK，CFL=0.9（p.2）",
            "results": "12 个合成算例上平均运行时间 96.4s→55.9s，降低 42%，"
                       "L2 误差在均匀基准 2% 以内（p.3, Fig.1/2）",
            "limitations": "全部为合成算例；指示子为启发式；并行扩展未测（p.4）",
        },
        "audience": "组会同行（合成示例）",
        "duration_min": 12,
        "slides": [
            {"kind": "title", "layout": title_layout,
             "title": "浅水求解器的自适应网格加密（合成示例）",
             "claim": "阈值 AMR 在合成算例套件上简单有效地加速求解",
             "bullets": ["A. Synthetic, B. Demo（虚构作者，合成演示）",
                         "组会汇报 · 12 分钟"],
             "figures": [],
             "evidence": [{"type": "page", "ref": "p.1",
                           "quote": "Title: Adaptive Grid Refinement for "
                                    "Shallow-Water Solvers"}],
             "notes": "开场 30 秒：说明这是合成演示论文，主线是"
                      "问题→方法→结果→限制。"},
            {"kind": "background", "layout": body_layout,
             "title": "研究背景与问题",
             "claim": "均匀网格在精度达标时计算代价过高",
             "bullets": [
                 "浅水方程常用均匀网格二阶有限体积求解（p.1）",
                 "目标：在等精度下降低运行时间（p.1 摘要）",
                 "加密判据：局部截断误差估计超过 1e-3 的细胞（p.1）"],
             "figures": [],
             "evidence": [{"type": "page", "ref": "p.1",
                           "quote": "refines cells where the estimated "
                                    "truncation error exceeds 1e-3"}],
             "notes": "1 分钟。强调问题定义与精度约束，数字 1e-3 逐字引自 p.1。"},
            {"kind": "method", "layout": body_layout,
             "title": "方法：阈值自适应加密",
             "claim": "误差指示子阈值驱动的四叉树 AMR",
             "bullets": [
                 "四叉树网格 + 二阶有限体积格式（p.2）",
                 "加密 eta_i > 1e-3；粗化 eta_i < 1e-4（p.2）",
                 "显式 Runge-Kutta 时间推进，CFL = 0.9（p.2）",
                 "实验环境：8 个合成计算节点（p.2）"],
             "figures": [],
             "evidence": [{"type": "page", "ref": "p.2",
                           "quote": "Refinement is triggered when the local "
                                    "error indicator eta_i > 1e-3"}],
             "notes": "2 分钟。讲清两个阈值与格式阶数；全部数字逐字引自 p.2。"},
            {"kind": "results", "layout": body_layout,
             "title": "结果：误差指示子分布（Figure 1）",
             "claim": "误差集中在局部区域，适合自适应加密",
             "bullets": [
                 "Figure 1 给出 12 个算例的误差指示子分布（p.3/p.5）",
                 "多数算例指示子量级在 1e-3 附近（Fig.1）"],
             "figures": [{"ref": "Figure 1",
                          "path": os.path.join(figs, "page-5.png"),
                          "caption": "Figure 1: error-indicator "
                                     "distribution (synthetic)"}],
             "evidence": [{"type": "figure", "ref": "Fig.1 / p.5",
                           "quote": "Figure 1 shows the error-indicator "
                                    "distribution over the domain"}],
             "notes": "2 分钟。指图说话：Figure 1 与正文引用一致。"},
            {"kind": "results", "layout": body_layout,
             "title": "结果：运行时间对比（Figure 2）",
             "claim": "AMR 平均运行时间降低 42%，精度损失可忽略",
             "bullets": [
                 "平均运行时间 96.4 s（均匀）→ 55.9 s（AMR）（p.3）",
                 "降幅 42%；L2 误差在均匀基准 2% 以内（p.3）",
                 "Figure 2 逐算例对比均匀与 AMR 运行时间（p.6）"],
             "figures": [{"ref": "Figure 2",
                          "path": os.path.join(figs, "page-6.png"),
                          "caption": "Figure 2: runtime per case, uniform "
                                     "vs AMR (synthetic)"}],
             "evidence": [{"type": "page", "ref": "p.3",
                           "quote": "mean runtime drops from 96.4 s "
                                    "(uniform) to 55.9 s (AMR), a 42% "
                                    "reduction"},
                          {"type": "figure", "ref": "Fig.2 / p.6",
                           "quote": "Figure 2 compares runtime per case."}],
             "notes": "3 分钟。核心结果页：96.4→55.9 s、42%、2% 三个数字"
                      "逐字引自 p.3。"},
            {"kind": "discussion", "layout": body_layout,
             "title": "讨论与限制",
             "claim": "结论仅适用于合成算例范围",
             "bullets": [
                 "全部算例为合成数据（p.4）",
                 "误差指示子为启发式（p.4）",
                 "并行扩展未在 8 节点以外测量（p.4）"],
             "figures": [],
             "evidence": [{"type": "page", "ref": "p.4",
                           "quote": "(1) all benchmarks are synthetic; "
                                    "(2) the error indicator is heuristic"}],
             "notes": "1.5 分钟。主动讲限制，避免过度claim。"},
            {"kind": "conclusion", "layout": body_layout,
             "title": "结论",
             "claim": "阈值 AMR 是浅水求解器简单有效的加速手段",
             "bullets": [
                 "等精度下运行时间降低 42%（12 个合成算例，p.3/p.4）",
                 "方法仅依赖一个可解释的误差阈值（p.2）",
                 "后续：真实算例验证与并行扩展测量（基于 p.4 限制）"],
             "figures": [],
             "evidence": [{"type": "page", "ref": "p.4",
                           "quote": "threshold-based AMR is a simple, "
                                    "effective acceleration for "
                                    "shallow-water solvers"}],
             "notes": "1 分钟收尾。回扣主线，强调适用范围为合成算例。"},
        ],
    }

    plan_path = os.path.join(args.work, "slide_plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"[fill_example_plan] wrote {len(plan['slides'])} slides, "
          f"layouts used: {sorted({s['layout'] for s in plan['slides']})} "
          f"(legal={len(legal)}) -> {plan_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
