#!/usr/bin/env python3
"""fill_example_plan.py — 自动填好 slide_plan.json（替代人工/Agent 创作步）。

仅用于 examples/ 合成演示。故意把 results 页塞入 12 条长要点（不写字号覆盖），
使导出渲染必然触发外圈 2% 边框带的 OVERFLOW 检查，从而演示
「溢出 → 阶梯降字号 → 必要时拆续页」的自动修复闭环。
"""
import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    args = ap.parse_args()
    plan_path = os.path.join(args.work, "slide_plan.json")
    with open(plan_path, encoding="utf-8") as f:
        plan = json.load(f)

    figs = plan.get("_candidates", {}).get("figures", [])
    fig1 = next((f for f in figs if "Figure 1" in f["ref"]), figs[0] if figs else None)
    fig2 = next((f for f in figs if "Figure 2" in f["ref"]), figs[-1] if figs else None)

    def fig_entry(f, caption):
        if not f:
            return None
        return {"ref": f["ref"], "path": f["path"], "caption": caption}

    slides = [
        {"kind": "title",
         "title": "渲染即交付：学术幻灯片的像素级证明",
         "claim": "pptx 只是中间态，导出件才是交付。",
         "bullets": ["基于合成论文《Render-Proof Pipelines for Academic Decks》",
                     "汇报人：Skill 自动演示（合成示例）"],
         "figures": [],
         "evidence": [{"type": "page", "ref": "p.1", "quote": "pixel-level render QA"}],
         "notes": "开场：强调『所见即导出』，本次汇报的全部页都经过逐页渲染核对。",
         "layout_hint": "Title Slide"},
        {"kind": "background",
         "title": "背景：导出环节才是事故现场",
         "claim": "构建期成功 ≠ 渲染正确。",
         "bullets": [
             "字体替换、文本裁切、图片丢失只在导出 PDF/PNG 后才出现",
             "128 decks 合成队列中，像素级 render QA 捕获 37 起溢出（28.9%）",
             "另有 11 起图片丢失（8.6%）是人工审查漏掉的",
             "既有工具链在构建期报告成功，没有一个校验渲染后的页面"],
         "figures": [],
         "evidence": [
             {"type": "page", "ref": "p.1",
              "quote": "pixel-level render QA caught 37 overflow events (28.9%)"},
             {"type": "page", "ref": "p.2",
              "quote": "Font substitution, clipped text and dropped images appear only after export"}],
         "notes": "用 28.9% / 8.6% 两个合成数字说明问题规模，提醒听众这些数字来自合成队列。",
         "layout_hint": "Title and Content"},
        {"kind": "method",
         "title": "方法：构建 → 导出 → 栅格 → 像素 QA",
         "claim": "把渲染件当作唯一事实来源。",
         "bullets": [
             "构建：python-pptx 按模板版式填占位符，占位符缺失走 textbox 兜底并记录",
             "导出：LibreOffice headless 转 PDF；pdftoppm 120dpi 栅格化（pymupdf 兜底）",
             "检查：墨迹进入外圈 2% 边框带 → 溢出；图区域空白 → 丢图；字体 diff fc-list",
             "修复：20-18-16-14-12 阶梯降字号，10pt 硬下限；仍溢出则拆「(续)」页"],
         "figures": [],
         "evidence": [{"type": "section", "ref": "§2 Methods / p.3",
                       "quote": "Fixes follow a 20-18-16-14-12 pt ladder with a hard 10 pt floor"}],
         "notes": "方法页只讲流水线四阶段与修复语义；阈值细节指向 references/render-qa.md。",
         "layout_hint": "Title and Content"},
        {"kind": "results",
         "title": "结果：缺陷分类统计（故意过载页）",
         "claim": "三类缺陷均可被像素检查稳定捕获。",
         # —— 故意过载：12 条长要点，触发 OVERFLOW → 修复循环 ——
         "bullets": [
             "溢出类缺陷 37/128（28.9%）：墨迹触碰页面外圈 2% 边框带即被标记，全部可复核",
             "图片丢失 11/128（8.6%）：构建日志记录的期望图区域渲染后接近空白即被标记",
             "字体替换 9 起：pptx XML 请求字体与 fc-list 现有字体逐一比对列出",
             "页数一致性 128/128：pptx 页数与导出 PDF 页数逐一相等，无一漂移",
             "修复成功率 41/48（85.4%）：三轮有界循环内完成，剩余 7 起如实报 partial",
             "阶梯降字号是最常用修复：大多数溢出在 18pt→16pt 一步内消失",
             "拆分续页是兜底手段：字号触及 10pt 硬下限仍溢出时后半要点移入「(续)」页",
             "所有修复写入 fix_log 与 result.json change_log，逐条可审计",
             "修复期间图片始终等比缩放，任何情况下不拉伸坐标轴与图例",
             "每页墨迹覆盖率留档：空渲染页（覆盖率 <0.05%）直接判 fail",
             "中位修复延迟 6.2 s/缺陷：重导出一册 8–10 页 deck 仅需数秒",
             "全部阈值与已知误报（全出血装饰、白底图）在 references/render-qa.md 中公开"],
         "figures": [],
         "evidence": [
             {"type": "page", "ref": "p.1",
              "quote": "repaired 41 of 48 defects (85.4%) within 3 iterations"},
             {"type": "page", "ref": "p.4",
              "quote": "Median repair latency was 6.2 s per defect"}],
         "notes": "本页故意过载，用于演示自动修复；修复后请以渲染件为准核对拆出的续页。",
         "layout_hint": "Title and Content"},
        {"kind": "results",
         "title": "结果：缺陷分类与修复延迟（图）",
         "claim": "图 1 与图 2 支撑前述统计。",
         "bullets": ["Figure 1：每类缺陷的检出次数；Figure 2：修复延迟分布",
                     "两图均为合成数据，仅用于演示渲染与证据映射"],
         "figures": [e for e in [
             fig_entry(fig1, "Figure 1: 缺陷分类（合成数据）"),
             fig_entry(fig2, "Figure 2: 修复延迟分布（合成数据）")] if e],
         "evidence": [{"type": "figure", "ref": "Figure 1 / p.5",
                       "quote": "Defect classes caught per deck (synthetic data)"},
                      {"type": "figure", "ref": "Figure 2 / p.6",
                       "quote": "Repair latency distribution across iterations (synthetic data)"}],
         "notes": "指图讲解：IMAGE-LOSS 检查保证这两张图在导出件中真实可见。",
         "layout_hint": "Title and Content"},
        {"kind": "discussion",
         "title": "讨论：误报边界与适用范围",
         "claim": "像素检查诚实标注自己的盲区。",
         "bullets": [
             "全出血（full-bleed）装饰横幅会触碰边框带 → 已知误报，需模板白名单",
             "白底为主的折线图可能低于图区域墨迹下限 → 降级为 warn 而非 fail",
             "两页类误报均记录在 render_proof.json，不静默通过",
             "page-count parity 在 128/128 合成册中保持"],
         "figures": [],
         "evidence": [{"type": "page", "ref": "p.4",
                       "quote": "decorative full-bleed banners trip the frame-band rule"}],
         "notes": "主动讲限制比被问出来更可信；评审可按 render-qa.md 复算阈值。",
         "layout_hint": "Title and Content"},
        {"kind": "conclusion",
         "title": "结论：每一页都可核",
         "claim": "导出件与源 pptx 的一致性可以逐页证明，而不是口头保证。",
         "bullets": [
             "页数一致性、溢出、丢图、字体替换、空页五类检查全部留档",
             "修复走公开阶梯，不硬塞：10pt 是硬下限，拆续页优先于压字号到不可读",
             "本页所在 deck 的 render_proof.json 即现场证据"],
         "figures": [],
         "evidence": [{"type": "page", "ref": "p.1",
                       "quote": "treat the pptx as an intermediate state and the render as truth"}],
         "notes": "收束：强调 render_proof.json 可交给第三方独立复跑。",
         "layout_hint": "Title and Content"},
    ]
    plan["slides"] = slides
    plan["mainline"] = {
        "problem": "构建期成功无法证明导出件正确（p.1–p.2）",
        "method": "导出→栅格→逐页像素 QA + 阶梯修复闭环（§2）",
        "results": "85.4% 缺陷三轮内修复，页数一致性 128/128（p.4, Fig.1–2）",
        "limitations": "全出血装饰与白底图存在已知误报（p.4）"}
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    print(f"[fill_example_plan] {len(slides)} 页计划完成；results 页故意过载 "
          f"({len(slides[3]['bullets'])} 条要点) 以演示修复闭环")


if __name__ == "__main__":
    main()
