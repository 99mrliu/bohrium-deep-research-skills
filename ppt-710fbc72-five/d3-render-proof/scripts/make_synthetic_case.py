#!/usr/bin/env python3
"""make_synthetic_case.py — 生成一个完全合成的演示案例（非真实论文）。

产物（写入 --out 指定的输入目录）：
  case.json                含 case_id 与 output_contract
  task.md                  任务说明
  materials/template.pptx  python-pptx 默认母版/版式/占位符（真实 OOXML 模板）
  materials/paper.pdf      matplotlib PdfPages 生成：4 页文字（含数字）+ 2 页图

本脚本只生成合成材料，用于 examples/ 演示与开发自检，不冒充正式案例。
"""
import argparse
import json
import os

PAPER_TITLE = "Synthetic Study: Render-Proof Pipelines for Academic Decks"
PAPER_TEXT_PAGES = [
    ("Abstract",
     "We study whether exported slides provably match their editable source. "
     "In a synthetic cohort of 128 decks, pixel-level render QA caught 37 overflow "
     "events (28.9%) and 11 lost images (8.6%) that manual review missed. "
     "Our render-proof loop repaired 41 of 48 defects (85.4%) within 3 iterations."),
    ("1. Introduction",
     "Academic presentations are usually judged by their pptx source, yet the "
     "deliverable that audiences actually see is the exported PDF or PNG. "
     "Font substitution, clipped text and dropped images appear only after export. "
     "Prior toolchains report success at build time; none verify the rendered page. "
     "We therefore treat the pptx as an intermediate state and the render as truth."),
    ("2. Methods",
     "The pipeline has four stages: build (python-pptx, template layouts), export "
     "(LibreOffice headless to PDF), rasterize (pdftoppm at 120 dpi), and per-page "
     "pixel QA. Overflow is flagged when ink enters the outer 2% frame band; image "
     "loss is flagged when an expected figure region is blank; fonts requested by "
     "the pptx XML are diffed against fc-list. Fixes follow a 20-18-16-14-12 pt "
     "ladder with a hard 10 pt floor; overflows that survive the floor split into "
     "continuation slides."),
    ("3. Results and Limitations",
     "Median repair latency was 6.2 s per defect; page-count parity held in "
     "128/128 decks. Two false-positive classes remain: decorative full-bleed "
     "banners trip the frame-band rule, and white-dominant plots can look blank "
     "to the image-loss floor. Both are documented with thresholds in "
     "references/render-qa.md. All numbers on this page are synthetic."),
]

FIG_PAGES = [
    ("Figure 1: Defect classes caught per deck (synthetic data).",
     "bar"),
    ("Figure 2: Repair latency distribution across iterations (synthetic data).",
     "hist"),
]


def build_template(path: str) -> None:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    prs = Presentation()  # default theme: real master + 11 layouts + placeholders
    # Stamp a title onto the slide master so template inheritance is visible.
    master = prs.slide_masters[0]
    for shp in master.shapes:
        if shp.is_placeholder and shp.placeholder_format.idx == 0:
            shp.text_frame.text = "Synthetic Template"
    # One example slide so the file is a realistic "starting deck".
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Synthetic Template — cover example"
    if len(s.placeholders) > 1:
        s.placeholders[1].text = "Replace me (auto-generated starting slide)"
    _ = Inches, Pt  # keep imports explicit for readers
    prs.save(path)


def build_paper(path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    with PdfPages(path) as pdf:
        for heading, body in PAPER_TEXT_PAGES:
            fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait
            fig.text(0.08, 0.93, PAPER_TITLE, fontsize=10, style="italic")
            fig.text(0.08, 0.86, heading, fontsize=16, weight="bold")
            fig.text(0.08, 0.78, body, fontsize=11, wrap=True,
                     va="top", ha="left")
            pdf.savefig(fig)
            plt.close(fig)
        for caption, kind in FIG_PAGES:
            fig, ax = plt.subplots(figsize=(8.27, 11.69))
            if kind == "bar":
                ax.bar(["overflow", "lost-image", "font-sub"], [37, 11, 9],
                       color=["#c0392b", "#2980b9", "#27ae60"])
                ax.set_ylabel("events per 128 decks")
                ax.set_title("Defect classes (synthetic)")
            else:
                import random
                rnd = random.Random(7)
                ax.hist([rnd.gauss(6.2, 1.4) for _ in range(300)], bins=24,
                        color="#2980b9")
                ax.set_xlabel("repair latency (s)")
                ax.set_title("Latency (synthetic)")
            fig.text(0.08, 0.06, caption, fontsize=11)
            pdf.savefig(fig)
            plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="输入目录（将写入 case.json/task.md/materials/）")
    args = ap.parse_args()
    out = os.path.abspath(args.out)
    mats = os.path.join(out, "materials")
    os.makedirs(mats, exist_ok=True)

    case = {
        "case_id": "synthetic-demo-03",
        "synthetic": True,
        "output_contract": {
            "fields": ["case_id", "status", "summary", "artifacts",
                       "evidence_map", "sources", "uncertainty", "change_log"]
        },
        "materials": {
            "paper_pdf": "materials/paper.pdf",
            "template_pptx": "materials/template.pptx",
        },
    }
    with open(os.path.join(out, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    task_md = """# 合成示例任务（synthetic-demo-03）

**这是合成示例，不是正式评测案例。**

请基于 `materials/paper.pdf`（合成论文）与 `materials/template.pptx`
（python-pptx 默认母版/版式）制作一份 8–10 页的学术汇报：

1. 提取研究问题、方法、结果、限制作为主线。
2. 每页给出 claim、要点、图引用与论文定位（页码/图号）。
3. 套用模板版式生成可编辑 pptx，附讲稿备注。
4. 导出 PDF/PNG 并逐页做像素级渲染 QA；溢出/丢图自动修复并留痕。

输出：deck.pptx、deck.pdf、preview/slide-N.png、render_proof.json、result.json。
"""
    with open(os.path.join(out, "task.md"), "w", encoding="utf-8") as f:
        f.write(task_md)

    build_template(os.path.join(mats, "template.pptx"))
    build_paper(os.path.join(mats, "paper.pdf"))
    print(f"[make_synthetic_case] wrote synthetic case to {out}")


if __name__ == "__main__":
    main()
