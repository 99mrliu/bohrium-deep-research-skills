#!/usr/bin/env python3
"""run_case.py — render-proof-deck 的两阶段单入口。

用法：
  python3 run_case.py prepare --input /input --work /app/work --output /app/output
  python3 run_case.py finish  --input /input --work /app/work --output /app/output

prepare：引导依赖 → 读 case.json/task.md/材料 → PyMuPDF 抽取论文（文本/页图/图候选）
  → 立即写 partial 骨架 result.json（含全部 contract 字段）→ 预填 slide_plan.json
  → 打印 NEXT ACTION（Agent 唯一需要创作的步骤：编辑 slide_plan.json）。
finish：校验 plan → 构建 deck.pptx → soffice 导出 PDF → 逐页像素 QA
  → 有界自动修复循环（≤3 轮）→ 最终渲染与报告 → 写齐 result.json。
"""
import argparse
import json
import os
import re
import subprocess
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)

BOOTSTRAP_NOTES = []


def bootstrap_deps():
    """缺依赖则 pip 安装；失败只记 degraded 不静默。"""
    need = {"pptx": "python-pptx", "PIL": "pillow", "fitz": "PyMuPDF"}
    for mod, pkg in need.items():
        try:
            __import__(mod)
        except ImportError:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", pkg],
                               check=True, capture_output=True, timeout=600)
                BOOTSTRAP_NOTES.append(f"已自动安装 {pkg}")
            except Exception as e:  # noqa: BLE001
                BOOTSTRAP_NOTES.append(f"degraded: 无法安装 {pkg}: {e}")


def _jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _jdump(o, p):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, ensure_ascii=False, indent=2)


def find_materials(input_dir, case):
    mats = dict(case.get("materials", {}))
    if "paper_pdf" not in mats:
        for root, _d, files in os.walk(input_dir):
            for fn in files:
                if fn.lower().endswith(".pdf") and "paper_pdf" not in mats:
                    mats["paper_pdf"] = os.path.relpath(os.path.join(root, fn), input_dir)
                if fn.lower().endswith(".pptx") and "template_pptx" not in mats:
                    mats["template_pptx"] = os.path.relpath(os.path.join(root, fn), input_dir)
    return mats


def extract_paper(pdf_path, work_dir):
    """PyMuPDF 抽取：逐页文本 + 每页渲染图 + 图候选页。"""
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    paper_dir = os.path.join(work_dir, "paper")
    pages_dir = os.path.join(paper_dir, "pages")
    figs_dir = os.path.join(paper_dir, "figs")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(figs_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    pages_text, figures = [], []
    for i, page in enumerate(doc):
        text = page.get_text("text")
        pages_text.append({"page": i + 1, "text": text})
        pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
        page_png = os.path.join(pages_dir, f"p{i + 1}.png")
        pix.save(page_png)
        # 图候选：正文提到 Figure/Fig. 的页 → 整页渲染作为可引用图
        refs = re.findall(r"(?:Figure|Fig\.?)\s*\d+", text)
        for k, ref in enumerate(refs):
            fp = os.path.join(figs_dir, f"p{i + 1}_fig{k + 1}.png")
            pix.save(fp)
            figures.append({"ref": ref, "page": i + 1, "path": fp})
    doc.close()
    full = "\n\n".join(f"--- p.{p['page']} ---\n{p['text']}" for p in pages_text)
    with open(os.path.join(paper_dir, "full_text.txt"), "w", encoding="utf-8") as f:
        f.write(full)
    _jdump(pages_text, os.path.join(paper_dir, "pages_text.json"))
    return pages_text, figures


def prefill_plan(work_dir, case, pages_text, figures, task_text):
    heads = []
    for p in pages_text:
        for line in p["text"].splitlines():
            s = line.strip()
            if re.match(r"^\d+(\.\d+)*\s+\S", s) and len(s) < 90:
                heads.append({"page": p["page"], "heading": s})
    numbers = []
    for p in pages_text:
        for m in re.findall(r"[^.。\n]*\d+(?:\.\d+)?%?[^.。\n]*", p["text"]):
            s = m.strip()
            if 12 < len(s) < 160:
                numbers.append({"page": p["page"], "quote": s})
    plan = {
        "mainline": {"problem": "", "method": "", "results": "", "limitations": ""},
        "audience": "学术同行（请按 task.md 调整）",
        "duration_min": 12,
        "slides": [
            {"kind": "title", "title": "", "claim": "", "bullets": [],
             "figures": [], "evidence": [], "notes": "", "layout_hint": "Title Slide"},
            {"kind": "background", "title": "", "claim": "", "bullets": [],
             "figures": [], "evidence": [], "notes": "", "layout_hint": "Title and Content"},
            {"kind": "method", "title": "", "claim": "", "bullets": [],
             "figures": [], "evidence": [], "notes": "", "layout_hint": "Title and Content"},
            {"kind": "results", "title": "", "claim": "", "bullets": [],
             "figures": [], "evidence": [], "notes": "", "layout_hint": "Title and Content"},
            {"kind": "discussion", "title": "", "claim": "", "bullets": [],
             "figures": [], "evidence": [], "notes": "", "layout_hint": "Title and Content"},
            {"kind": "conclusion", "title": "", "claim": "", "bullets": [],
             "figures": [], "evidence": [], "notes": "", "layout_hint": "Title and Content"},
        ],
        "_candidates": {
            "section_headings": heads[:20],
            "figures": [{"ref": f["ref"], "page": f["page"], "path": f["path"]}
                        for f in figures[:10]],
            "number_quotes": numbers[:20],
            "task_excerpt": task_text[:600],
        },
        "_rules": [
            "数字必须与原文逐字一致；找不到出处的内容不上页",
            "图号与正文引用一致；讲稿写入 notes",
            "正文默认 18pt；渲染 QA 发现溢出会自动按阶梯降字号（下限 10pt）或拆续页",
        ],
    }
    _jdump(plan, os.path.join(work_dir, "slide_plan.json"))


def cmd_prepare(args):
    bootstrap_deps()
    input_dir, work_dir, output_dir = args.input, args.work, args.output
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    case = _jload(os.path.join(input_dir, "case.json"))
    task_text = ""
    tp = os.path.join(input_dir, "task.md")
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as f:
            task_text = f.read()
    mats = find_materials(input_dir, case)

    pages_text, figures = [], []
    paper = mats.get("paper_pdf")
    if paper and os.path.exists(os.path.join(input_dir, paper)):
        pages_text, figures = extract_paper(os.path.join(input_dir, paper), work_dir)
    else:
        BOOTSTRAP_NOTES.append("degraded: 未找到论文 PDF，抽取跳过")

    # partial-first：立即写诚实骨架
    import make_result
    make_result.finalize(
        input_dir, work_dir, output_dir, status="partial",
        summary="prepare 完成：材料已抽取，slide_plan.json 已预填骨架，等待 Agent 完成页计划。",
        change_log=["[prepare] 依赖自检: " + ("; ".join(BOOTSTRAP_NOTES) or "全部就绪"),
                    f"[prepare] 抽取论文 {len(pages_text)} 页，图候选 {len(figures)} 个"],
        uncertainty=["页级主张与要点尚未填写（等待 slide_plan.json）",
                     "尚未构建/渲染，导出一致性未验证"])

    prefill_plan(work_dir, case, pages_text, figures, task_text)
    print("=" * 70)
    print("[prepare] 完成。已写出：")
    print(f"  - {output_dir}/result.json        (status=partial 骨架)")
    print(f"  - {work_dir}/slide_plan.json      (预填骨架 + 抽取候选)")
    print(f"  - {work_dir}/paper/               (全文/页文本/页图/图候选)")
    print("NEXT ACTION: 编辑 slide_plan.json —— 为每页填 title/claim/bullets/")
    print("  figures(用 _candidates.figures 的路径)/evidence(页码或图号+逐字 quote)/")
    print("  notes，然后运行：")
    print(f"  python3 {os.path.join(SCRIPTS, 'run_case.py')} finish "
          f"--input {input_dir} --work {work_dir} --output {output_dir}")
    print("=" * 70)


def cmd_finish(args):
    bootstrap_deps()
    input_dir, work_dir, output_dir = args.input, args.work, args.output
    case = _jload(os.path.join(input_dir, "case.json"))
    mats = find_materials(input_dir, case)
    plan_path = os.path.join(work_dir, "slide_plan.json")
    if not os.path.exists(plan_path):
        print("[finish] 缺少 slide_plan.json，请先运行 prepare 并完成计划", file=sys.stderr)
        sys.exit(2)
    plan = _jload(plan_path)
    change_log = []
    lint = []
    kinds = [s.get("kind") for s in plan.get("slides", [])]
    for need in ("title", "conclusion"):
        if need not in kinds:
            lint.append(f"plan 缺少页型 {need}")
    if not plan.get("slides"):
        print("[finish] slide_plan.json 没有任何页", file=sys.stderr)
        sys.exit(2)
    for w in lint:
        change_log.append("[plan-lint warn] " + w)

    template = mats.get("template_pptx")
    template_path = os.path.join(input_dir, template) if template else None
    if not template_path or not os.path.exists(template_path):
        change_log.append("[finish] 未找到模板 pptx，使用 python-pptx 默认模板")
        from pptx import Presentation
        template_path = os.path.join(work_dir, "default_template.pptx")
        Presentation().save(template_path)

    import build_deck
    import fix_loop
    import make_result
    import render_pipeline

    build_deck.build(plan_path, template_path,
                     os.path.join(work_dir, "deck.pptx"),
                     os.path.join(work_dir, "build_log.json"))
    change_log.append(f"[finish] 构建 deck.pptx：{len(plan['slides'])} 页")

    # 保留历史 fix_log 与 run 号，保证幂等重跑可对照
    old = {}
    rp = os.path.join(output_dir, "render_proof.json")
    if os.path.exists(rp):
        old = _jload(rp)
    proof = render_pipeline.render_and_qa(
        work_dir, output_dir, fix_log=old.get("fix_log", []),
        run=int(old.get("run", 0)) + 1)
    change_log.append(f"[finish] 首轮渲染 QA overall={proof['overall']} "
                      f"失败项 {len(proof['failures'])} 个")

    if proof["failures"]:
        overall, fix_log, unfixable = fix_loop.run_fix_loop(
            work_dir, output_dir, template_path)
        proof = _jload(rp)
    else:
        unfixable = proof.get("unfixable", [])

    # 历史修复（含上一轮 finish 的）统一汇总进 change_log，重跑不丢痕
    for f in proof.get("fix_log", []):
        if f.get("type") != "unfixable":
            change_log.append(
                f"[render-fix it{f.get('iteration')} p{f.get('page')}] "
                f"{f.get('type')}: {f.get('detail')}")
    for u in unfixable:
        change_log.append(f"[render-fix unfixable p{u['page']}] {u['check']}: {u['reason']}")

    # 终态交付：deck 复制到 output（pptx 可编辑 + PDF/PNG 预览同目录可复核）
    import shutil
    shutil.copy2(os.path.join(work_dir, "deck.pptx"),
                 os.path.join(output_dir, "deck.pptx"))

    overall = proof.get("overall", "fail")
    if overall in ("pass", "warn") and not unfixable:
        status = "success"
    elif overall in ("pass", "warn") or proof.get("pages"):
        status = "partial"
    else:
        status = "failed"
    uncertainty = []
    if proof["renderer"]["degraded"]:
        uncertainty.append("渲染链路降级：" + "; ".join(proof["renderer"]["notes"]))
    if proof["fonts"]["missing"]:
        uncertainty.append("字体缺失将被替换：" + ", ".join(proof["fonts"]["missing"]))
    if unfixable:
        uncertainty.append("未修复页：" +
                           "; ".join(f"p{u['page']}({u['check']})" for u in unfixable))
    uncertainty.append("外圈 2% 边框带规则对全出血装饰版式可能误报（见 references/render-qa.md）")

    summary = (f"{len(proof.get('pages', []))} 页渲染 QA overall={overall}；"
               f"页数一致性 {proof['page_count']['status']}；"
               f"自动修复 {len([f for f in proof.get('fix_log', []) if f.get('type') != 'unfixable'])} 处；"
               f"未修复 {len(unfixable)} 处。")
    make_result.finalize(
        input_dir, work_dir, output_dir, status=status, summary=summary,
        change_log=change_log, uncertainty=uncertainty,
        extra_evidence={"render_proof": "render_proof.json",
                        "overall": overall, "runs": proof.get("run", 1)})

    print("=" * 70)
    print(f"[finish] status={status} overall={overall}")
    print("逐页核对清单：")
    for p in proof.get("pages", []):
        c = p["checks"]
        imgs = ",".join(f"{i['ref']}:{i['status']}" for i in c["images"]) or "-"
        print(f"  p{p['page']:>2} ink={p['ink_coverage']:.4f} "
              f"overflow={c['overflow']['status']} images={imgs}")
    print(f"产物：{output_dir}/deck.pptx, deck.pdf, preview/, render_proof.json, result.json")
    print("=" * 70)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("prepare", "finish"):
        sp = sub.add_parser(name)
        sp.add_argument("--input", required=True)
        sp.add_argument("--work", required=True)
        sp.add_argument("--output", required=True)
    args = ap.parse_args()
    (cmd_prepare if args.cmd == "prepare" else cmd_finish)(args)


if __name__ == "__main__":
    main()
