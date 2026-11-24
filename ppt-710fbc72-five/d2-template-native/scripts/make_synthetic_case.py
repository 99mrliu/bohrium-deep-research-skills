#!/usr/bin/env python3
"""Generate a fully SYNTHETIC demo case for template-native-deck.

All generated files are synthetic (marked as such) and must be written to a
temporary/output directory — never into the bundle itself.

Outputs into OUT_DIR:
  template.pptx       real OOXML template whose theme is customized at XML
                      level (distinct major/minor latin+ea fonts, custom
                      accent1 color) so theme preservation is auditable.
  starting_deck.pptx  same template + 2 stale slides that must be deleted.
  paper.pdf           6-page synthetic paper (4 text pages + Figure 1/2).
  case.json, task.md  harness-style inputs.

Usage:
    python3 make_synthetic_case.py OUT_DIR
"""
import json
import os
import shutil
import sys
import tempfile
import zipfile

# Custom theme applied at XML level so theme preservation is auditable:
#   majorFont latin/ea, minorFont latin/ea, accent1 color.
CUSTOM_MAJOR_LATIN = "Georgia"
CUSTOM_MAJOR_EA = "SimHei"
CUSTOM_MINOR_LATIN = "Trebuchet MS"
CUSTOM_MINOR_EA = "KaiTi"
CUSTOM_ACCENT1 = "8E44AD"


def _set_font(text: str, font_block: str, attr: str, value: str) -> str:
    """Replace the first <a:{attr} typeface="..."/> inside <a:{font_block}>."""
    import re
    m = re.search(r"<a:%s>.*?</a:%s>" % (font_block, font_block),
                  text, re.S)
    if not m:
        raise RuntimeError(f"theme has no {font_block} block")
    block = m.group(0)
    new_block, n = re.subn(r'(<a:%s typeface=")[^"]*(")' % attr,
                           r"\g<1>%s\g<2>" % value, block, count=1)
    if n != 1:
        raise RuntimeError(f"no {attr} typeface in {font_block}")
    return text.replace(block, new_block, 1)


def _set_accent1(text: str, value: str) -> str:
    import re
    m = re.search(r"<a:accent1>.*?</a:accent1>", text, re.S)
    if not m:
        raise RuntimeError("theme has no accent1")
    block = m.group(0)
    new_block, n = re.subn(r'val="[0-9A-Fa-f]{6}"', f'val="{value}"',
                           block, count=1)
    if n != 1:
        raise RuntimeError("no srgbClr val in accent1")
    return text.replace(block, new_block, 1)

PAPER_PAGES = [
    # (page_number, [lines])  -- text pages
    ("Synthetic Paper — DO NOT CITE (page {p})\n\n"
     "Title: Adaptive Grid Refinement for Shallow-Water Solvers\n"
     "Authors: A. Synthetic, B. Demo (fictional)\n\n"
     "Abstract. We study adaptive mesh refinement (AMR) for the "
     "shallow-water equations. Our method refines cells where the "
     "estimated truncation error exceeds 1e-3. On the synthetic "
     "benchmark suite of 12 cases, AMR reduces runtime by 42% at "
     "equal accuracy compared with uniform grids."),
    ("Page {p} — Method\n\n"
     "The solver uses a second-order finite-volume scheme on a "
     "quadtree grid. Refinement is triggered when the local error "
     "indicator eta_i > 1e-3; coarsening when eta_i < 1e-4. "
     "Time stepping uses explicit Runge-Kutta with CFL = 0.9. "
     "All experiments run on 8 synthetic compute nodes."),
    ("Page {p} — Results\n\n"
     "Figure 1 shows the error-indicator distribution over the "
     "domain. Across the 12 synthetic benchmark cases, mean runtime "
     "drops from 96.4 s (uniform) to 55.9 s (AMR), a 42% reduction, "
     "while the L2 error stays within 2% of the uniform baseline. "
     "Figure 2 compares runtime per case."),
    ("Page {p} — Limitations and Conclusion\n\n"
     "Limitations: (1) all benchmarks are synthetic; (2) the error "
     "indicator is heuristic; (3) parallel scaling was not measured "
     "beyond 8 nodes. Conclusion: threshold-based AMR is a simple, "
     "effective acceleration for shallow-water solvers on the tested "
     "synthetic suite."),
]


def _rewrite_zip_member(src_zip, dst_zip, member, transform):
    with src_zip.open(member) as f:
        data = f.read()
    dst_zip.writestr(member, transform(data))


def customize_theme(src_pptx: str, dst_pptx: str) -> None:
    """Copy src pptx, rewriting theme1.xml with the custom fonts/color."""

    def transform(data: bytes) -> bytes:
        text = data.decode("utf-8")
        text = _set_font(text, "majorFont", "latin", CUSTOM_MAJOR_LATIN)
        text = _set_font(text, "majorFont", "ea", CUSTOM_MAJOR_EA)
        text = _set_font(text, "minorFont", "latin", CUSTOM_MINOR_LATIN)
        text = _set_font(text, "minorFont", "ea", CUSTOM_MINOR_EA)
        text = _set_accent1(text, CUSTOM_ACCENT1)
        return text.encode("utf-8")

    with zipfile.ZipFile(src_pptx) as zin, \
            zipfile.ZipFile(dst_pptx, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "ppt/theme/theme1.xml":
                _rewrite_zip_member(zin, zout, item, transform)
            else:
                zout.writestr(item, zin.read(item.filename))


def make_template(out_dir: str) -> str:
    from pptx import Presentation
    tmp = tempfile.mkdtemp(prefix="tnd-tpl-")
    raw = os.path.join(tmp, "raw.pptx")
    Presentation().save(raw)
    path = os.path.join(out_dir, "template.pptx")
    customize_theme(raw, path)
    # verify the customization landed
    with zipfile.ZipFile(path) as z:
        theme = z.read("ppt/theme/theme1.xml").decode("utf-8")
    for token in (CUSTOM_MAJOR_LATIN, CUSTOM_MAJOR_EA, CUSTOM_MINOR_LATIN,
                  CUSTOM_MINOR_EA, CUSTOM_ACCENT1):
        if token not in theme:
            raise RuntimeError(f"theme customization missing: {token}")
    shutil.rmtree(tmp, ignore_errors=True)
    return path


def make_starting_deck(template_path: str, out_dir: str) -> str:
    """Same template plus 2 stale slides (python-pptx round-trips the theme
    part byte-identically, verified by the example run's audit)."""
    from pptx import Presentation
    prs = Presentation(template_path)
    layout = prs.slide_masters[0].slide_layouts[1]  # Title and Content
    for i in (1, 2):
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text = f"STALE SLIDE {i} — DELETE ME (synthetic)"
        body = next(ph for ph in slide.placeholders
                    if ph.placeholder_format.idx != 0)
        body.text = "Placeholder content from an old, unrelated deck."
    path = os.path.join(out_dir, "starting_deck.pptx")
    prs.save(path)
    return path


def make_paper(out_dir: str) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    path = os.path.join(out_dir, "paper.pdf")
    with PdfPages(path) as pdf:
        for p, text in enumerate(PAPER_PAGES, start=1):
            fig = plt.figure(figsize=(8.27, 11.69))  # A4
            fig.text(0.08, 0.95, text.format(p=p), va="top", ha="left",
                     fontsize=10, wrap=True, family="serif")
            fig.text(0.5, 0.03, f"- {p} -", ha="center", fontsize=9)
            pdf.savefig(fig)
            plt.close(fig)
        # Figure 1 (page 5)
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.set_position([0.15, 0.55, 0.7, 0.3])
        xs = list(range(1, 13))
        ax.semilogy(xs, [10 ** (-3.2 + 0.05 * ((x * 7) % 5)) for x in xs], "o-")
        ax.set_xlabel("benchmark case")
        ax.set_ylabel("error indicator eta")
        ax.set_title("Figure 1: error-indicator distribution (synthetic)")
        pdf.savefig(fig)
        plt.close(fig)
        # Figure 2 (page 6)
        fig, ax = plt.subplots(figsize=(8.27, 11.69))
        ax.set_position([0.15, 0.55, 0.7, 0.3])
        uniform = [90 + (x * 13) % 25 for x in xs]
        amr = [round(u * 0.58, 1) for u in uniform]
        w = 0.38
        ax.bar([x - w / 2 for x in xs], uniform, width=w, label="uniform")
        ax.bar([x + w / 2 for x in xs], amr, width=w, label="AMR")
        ax.set_xlabel("benchmark case")
        ax.set_ylabel("runtime (s)")
        ax.legend()
        ax.set_title("Figure 2: runtime per case, uniform vs AMR (synthetic)")
        pdf.savefig(fig)
        plt.close(fig)
    return path


def main(argv=None):
    out_dir = (argv or sys.argv[1:])[0] if (argv or sys.argv[1:]) else None
    if not out_dir:
        print("usage: make_synthetic_case.py OUT_DIR", file=sys.stderr)
        return 2
    os.makedirs(out_dir, exist_ok=True)

    tpl = make_template(out_dir)
    deck = make_starting_deck(tpl, out_dir)
    paper = make_paper(out_dir)

    case = {
        "case_id": "synthetic-demo-02",
        "synthetic": True,
        "output_contract": {
            "fields": ["case_id", "status", "summary", "artifacts",
                       "evidence_map", "sources", "uncertainty", "change_log"]
        },
        "materials": {
            "template": "template.pptx",
            "starting_deck": "starting_deck.pptx",
            "paper": "paper.pdf",
        },
    }
    with open(os.path.join(out_dir, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False, indent=2)

    task_md = """# 任务说明（合成示例 / SYNTHETIC DEMO — 非正式案例）

围绕合成论文 `paper.pdf`（虚构研究，仅供流程演示）制作学术汇报 PPT：

1. 以 `template.pptx` 为模板（主题字体 Georgia/Trebuchet MS + SimHei，强调色 #8E44AD）。
2. `starting_deck.pptx` 是起始稿，内含 2 页过期页面，必须删除后在其模板体系上重建。
3. 提取论文主线（问题/方法/结果/限制），组织 title→conclusion 页结构。
4. Figure 1 / Figure 2 必须出现在结果页，图号与正文引用一致。
5. 每页保留论文定位（页码/图号）作为证据；讲稿写入备注。
6. 交付可编辑 pptx + PDF 渲染 + 逐页继承审计报告。

约束：12 分钟汇报，面向组会同行；数字必须与原文逐字一致；找不到出处的内容不上页。
"""
    with open(os.path.join(out_dir, "task.md"), "w", encoding="utf-8") as f:
        f.write(task_md)

    print(f"[make_synthetic_case] wrote synthetic case to {out_dir}:")
    for p in (tpl, deck, paper):
        print(f"  {os.path.basename(p)} ({os.path.getsize(p)} bytes)")
    print("  case.json, task.md")
    print("  NOTE: all files are SYNTHETIC demo material, not a real case.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
