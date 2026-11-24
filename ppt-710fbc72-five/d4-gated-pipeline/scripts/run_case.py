#!/usr/bin/env python3
"""run_case.py — gated-pipeline-deck 阶段机入口。

子命令：
  prepare   跑 S0→S4：引导依赖、读输入、抽取论文、解剖模板、预填 slide_plan.json，
            并在 S1 后立即写出诚实的 partial /app/output/result.json。
  finish    跑 S0→S9：凡检查点有效且输入未变的阶段自动跳过（断点续跑），
            依次过 plan-gate、构建 deck、导出渲染、QA 门禁、finalize。
  status    只读：打印各阶段状态、门禁状态、下一步恢复提示。

阶段契约见 references/pipeline-contract.md。
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

sys.dont_write_bytecode = True  # 不在 skill 安装目录产生 __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stage_machine as sm
from stage_machine import Ctx, StageFailure, now_iso, read_json, write_json, sha256_file

NUM_RE = re.compile(r"\d+(?:\.\d+)?%?")
SECTION_HEADER_RE = re.compile(r"^\d+(\.\d+)*\s*[.:]?\s*[A-Z\u4e00-\u9fff]\w*(\s+[A-Za-z\u4e00-\u9fff]\w*){0,3}$")

# ---------------------------------------------------------------- S0


def stage_S0(ctx: Ctx):
    """引导依赖：缺 python 包则尝试 pip 安装；探测 soffice/pdftoppm；记 degraded。"""
    need_pip = []
    for mod, pkg in [("pptx", "python-pptx"), ("pymupdf", "PyMuPDF"), ("PIL", "pillow")]:
        try:
            __import__(mod)
        except ImportError:
            try:
                __import__("fitz" if mod == "pymupdf" else mod)
            except ImportError:
                need_pip.append(pkg)
    pip_log = []
    if need_pip:
        print(f"[S0] 缺少 python 包 {need_pip}，尝试 pip install ...", flush=True)
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", *need_pip],
                           capture_output=True, text=True, timeout=600)
        pip_log.append({"cmd": "pip install " + " ".join(need_pip), "returncode": r.returncode,
                        "stderr_tail": (r.stderr or "")[-500:]})
        if r.returncode != 0:
            print("[S0] pip 安装失败，记 degraded（后续阶段若缺包会给出精确失败）", flush=True)
    state = sm.detect_tools()
    state["pip_install_log"] = pip_log
    path = os.path.join(ctx.work, "tools.json")
    write_json(path, state)
    for d in state["degraded_tools"]:
        print(f"[S0] degraded: {d}", flush=True)
    return [path]


# ---------------------------------------------------------------- S1


def _declared_material(ctx: Ctx, case: dict, key: str):
    """从 case.json 声明中找材料路径（materials 可为 dict/list/str），必须真实存在。"""
    mats = case.get("materials") or case.get("material") or {}
    candidates = []
    if isinstance(mats, dict):
        v = mats.get(key)
        if isinstance(v, str):
            candidates.append(v)
        elif isinstance(v, list):
            candidates.extend(x for x in v if isinstance(x, str))
    elif isinstance(mats, list):
        for m in mats:
            if isinstance(m, str) and key in os.path.basename(m).lower():
                candidates.append(m)
            elif isinstance(m, dict) and m.get("role") == key and isinstance(m.get("path"), str):
                candidates.append(m["path"])
    for rel in candidates:
        p = rel if os.path.isabs(rel) else os.path.join(ctx.input_dir, rel)
        if os.path.isfile(p):
            return os.path.abspath(p)
    return None


def stage_S1(ctx: Ctx):
    """读 case.json/task.md/全部输入材料并做 sha256 台账；立即写 partial result.json。"""
    case_path = os.path.join(ctx.input_dir, "case.json")
    if not os.path.isfile(case_path):
        raise StageFailure(
            f"输入目录缺少 case.json: {ctx.input_dir}",
            hint=f"确认评测输入挂载在 {ctx.input_dir}（应含 case.json 与 task.md）后重跑 prepare")
    case = read_json(case_path, default=None)
    if not isinstance(case, dict):
        raise StageFailure(f"case.json 不是合法 JSON 对象: {case_path}")
    case_id = case.get("case_id") or "unknown-case"
    fields = list((case.get("output_contract") or {}).get("fields") or [])
    for f in ("case_id", "status", "sources", "uncertainty", "change_log"):
        if f not in fields:
            fields.append(f)  # 平台运行时契约要求的保底字段

    files = []
    for root, _dirs, names in os.walk(ctx.input_dir):
        for fn in sorted(names):
            p = os.path.join(root, fn)
            files.append({"path": os.path.relpath(p, ctx.input_dir),
                          "bytes": os.path.getsize(p), "sha256": sha256_file(p)})
    files.sort(key=lambda x: x["path"])

    pdfs, templates, others = [], [], []
    for f in files:
        p = os.path.join(ctx.input_dir, f["path"])
        low = f["path"].lower()
        if low.endswith(".pdf"):
            pdfs.append(p)
        elif low.endswith((".pptx", ".potx")):
            templates.append(p)
        elif low not in ("case.json", "task.md"):
            others.append(p)
    paper = _declared_material(ctx, case, "paper") or (pdfs[0] if pdfs else None)
    template = _declared_material(ctx, case, "template") or (templates[0] if templates else None)

    task_path = os.path.join(ctx.input_dir, "task.md")
    task_excerpt = ""
    if os.path.isfile(task_path):
        with open(task_path, "r", encoding="utf-8", errors="replace") as fh:
            task_excerpt = fh.read(4000)

    inventory = {
        "case_id": case_id,
        "output_contract_fields": fields,
        "input_dir": ctx.input_dir,
        "files": files,
        "paper": paper,
        "template": template,
        "other_pdfs": [p for p in pdfs if p != paper],
        "other_files": others,
        "task_md_present": os.path.isfile(task_path),
        "task_md_excerpt": task_excerpt[:1200],
        "read_at": now_iso(),
    }
    inv_path = os.path.join(ctx.work, "inputs_inventory.json")
    write_json(inv_path, inventory)

    # partial-first：S1 完成后 result.json 必须已经是合法诚实 partial。
    sources = [{"path": f["path"], "sha256": f["sha256"],
                "role": ("paper" if os.path.join(ctx.input_dir, f["path"]) == paper
                         else "template" if os.path.join(ctx.input_dir, f["path"]) == template
                         else "input")} for f in files]
    placeholders = {
        "case_id": case_id,
        "status": "partial",
        "summary": "(partial) 已完成 S1 输入读取；内容抽取、模板解剖、构建与导出尚未运行。",
        "artifacts": [],
        "evidence_map": [],
        "sources": sources,
        "uncertainty": ["S2-S9 尚未完成：本结果为过程 partial，缺 deck/导出/QA 结论。"],
        "change_log": [{"stage": "S1", "at": now_iso(),
                        "note": "read inputs; wrote honest partial result.json skeleton"}],
    }
    result = read_json(ctx.result_path(), default={}) or {}
    for f in fields:
        if f in placeholders:
            result[f] = placeholders[f]
        elif f not in result:
            result[f] = f"(pending: {f} 将在后续阶段填写)"
    result["case_id"] = case_id
    result["status"] = "partial"
    write_json(ctx.result_path(), result)

    if not os.path.isfile(ctx.qa_gates_path()):
        sm.init_qa_gates(ctx, case_id)
    return [inv_path, ctx.result_path(), ctx.qa_gates_path()]


# ---------------------------------------------------------------- S2


def stage_S2(ctx: Ctx):
    """PyMuPDF 抽取论文逐页文本与图（内嵌位图优先，矢量图退化为整页渲染）。"""
    inv = read_json(os.path.join(ctx.work, "inputs_inventory.json"), default={})
    paper = (inv or {}).get("paper")
    if not paper or not os.path.isfile(paper):
        raise StageFailure(
            "未找到论文 PDF（case.json 未声明且输入目录无 .pdf）",
            hint=f"把论文 PDF 放入 {ctx.input_dir} 或在 case.json materials.paper 中声明后重跑 prepare")
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf
        except ImportError:
            raise StageFailure("缺少 PyMuPDF", hint="pip install PyMuPDF 后重跑 prepare")

    outdir = os.path.join(ctx.work, "paper")
    pages_dir = os.path.join(outdir, "pages")
    figs_dir = os.path.join(outdir, "figs")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(figs_dir, exist_ok=True)

    doc = pymupdf.open(paper)
    page_infos, figures, num_candidates, page_text_files = [], [], [], []
    all_text = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        text = page.get_text("text") or ""
        pno = i + 1
        pt = os.path.join(pages_dir, f"page_{pno:03d}.txt")
        with open(pt, "w", encoding="utf-8") as fh:
            fh.write(text)
        page_text_files.append(pt)
        all_text.append(text)
        labels = re.findall(r"(?:Figure|Fig\.?|图)\s*\d+", text)
        # 图注（带冒号）才视作"本页含图"：避免把正文里 "Figure 1 shows ..." 的提及当图页
        caption_labels = re.findall(r"(?:Figure|Fig\.?|图)\s*\d+(?=\s*[:：])", text)
        saved = 0
        for img in page.get_images(full=True):
            try:
                xref = img[0]
                info = doc.extract_image(xref)
                w, h = info.get("width", 0), info.get("height", 0)
                if w * h < 40000:
                    continue
                ext = info.get("ext", "png")
                fp = os.path.join(figs_dir, f"p{pno}_img{saved}.{ext}")
                with open(fp, "wb") as fh:
                    fh.write(info["image"])
                label = labels[saved] if saved < len(labels) else f"p{pno}-img{saved}"
                figures.append({"label": label, "page": pno, "path": fp, "source": "embedded"})
                saved += 1
            except (KeyError, ValueError, OSError):
                continue
        if caption_labels and saved == 0:
            # 矢量图（如 matplotlib 生成）：整页 150dpi 渲染作为图证据候选
            labels = caption_labels
            fp = os.path.join(figs_dir, f"p{pno}_figpage.png")
            pix = page.get_pixmap(dpi=150)
            pix.save(fp)
            figures.append({"label": labels[0], "page": pno, "path": fp, "source": "page-render",
                            "note": "矢量图页整页渲染（含坐标轴/图注）"})
        for line in text.splitlines():
            s = " ".join(line.split())
            if len(s) >= 8 and NUM_RE.search(s):
                num_candidates.append({"page": pno, "tokens": NUM_RE.findall(s)[:6], "line": s[:220]})
        page_infos.append({"page": pno, "chars": len(text), "n_images": saved})

    paper_text_path = os.path.join(outdir, "paper_text.txt")
    with open(paper_text_path, "w", encoding="utf-8") as fh:
        fh.write("\n\n".join(all_text))
    extract = {
        "pdf": paper,
        "pdf_sha256": sha256_file(paper),
        "pages": doc.page_count,
        "page_infos": page_infos,
        "page_text_files": page_text_files,
        "paper_text": paper_text_path,
        "figures": figures,
        "num_candidates": num_candidates[:80],
        "extracted_at": now_iso(),
    }
    doc.close()
    ex_path = os.path.join(outdir, "extract.json")
    write_json(ex_path, extract)
    outputs = [ex_path, paper_text_path] + [f["path"] for f in figures]
    return outputs


# ---------------------------------------------------------------- S3


def stage_S3(ctx: Ctx):
    """解剖模板：母版/版式/占位符清单、页面尺寸、现有页数。"""
    inv = read_json(os.path.join(ctx.work, "inputs_inventory.json"), default={})
    template = (inv or {}).get("template")
    if not template or not os.path.isfile(template):
        raise StageFailure(
            "未找到模板 pptx（case.json 未声明且输入目录无 .pptx/.potx）",
            hint=f"把模板放入 {ctx.input_dir} 或在 case.json materials.template 中声明后重跑 prepare")
    try:
        from pptx import Presentation
    except ImportError:
        raise StageFailure("缺少 python-pptx", hint="pip install python-pptx 后重跑 prepare")
    prs = Presentation(template)
    layouts = []
    for idx, lo in enumerate(prs.slide_layouts):
        phs = []
        for ph in lo.placeholders:
            phs.append({"idx": ph.placeholder_format.idx,
                        "type": str(ph.placeholder_format.type),
                        "name": ph.name})
        layouts.append({"index": idx, "name": lo.name, "placeholders": phs})
    report = {
        "template": template,
        "template_sha256": sha256_file(template),
        "slide_width_emu": int(prs.slide_width),
        "slide_height_emu": int(prs.slide_height),
        "slide_count": len(prs.slides._sldIdLst),
        "master_count": len(prs.slide_masters),
        "layouts": layouts,
        "layout_names": [lo["name"] for lo in layouts],
        "dissected_at": now_iso(),
    }
    rp = os.path.join(ctx.work, "template_report.json")
    write_json(rp, report)
    return [rp]


# ---------------------------------------------------------------- S4


def _pick_line(ctx: Ctx, page_no: int, prefer=()):
    """从某页挑一行可引用文本（优先含关键词），供预填骨架做证据锚点。"""
    pt = os.path.join(ctx.work, "paper", "pages", f"page_{page_no:03d}.txt")
    if not os.path.isfile(pt):
        return None
    with open(pt, "r", encoding="utf-8") as fh:
        lines = [" ".join(x.split()) for x in fh.read().splitlines()]
    lines = [x for x in lines if len(x) >= 12 and not SECTION_HEADER_RE.match(x)]
    if not lines:
        return None
    for kw in prefer:
        for x in lines:
            if kw.lower() in x.lower():
                return x
    return lines[0]


def _pick_line_across(ctx: Ctx, page_nos, prefer=()):
    """跨页按关键词找可引用行；返回 (page_no, line) 或 (None, None)。"""
    for pno in page_nos:
        pt = os.path.join(ctx.work, "paper", "pages", f"page_{pno:03d}.txt")
        if not os.path.isfile(pt):
            continue
        with open(pt, "r", encoding="utf-8") as fh:
            lines = [" ".join(x.split()) for x in fh.read().splitlines()]
        lines = [x for x in lines if len(x) >= 12 and not SECTION_HEADER_RE.match(x)]
        for kw in prefer:
            for x in lines:
                if kw.lower() in x.lower():
                    return pno, x
    return None, None


def stage_S4(ctx: Ctx):
    """预填 slide_plan.json 骨架（含证据锚点候选），然后 STOP 等待 Agent 编辑。"""
    extract = read_json(os.path.join(ctx.work, "paper", "extract.json"), default=None)
    tpl = read_json(os.path.join(ctx.work, "template_report.json"), default=None)
    if not extract or not tpl:
        raise StageFailure("缺少 S2/S3 产物", hint=ctx.default_resume_cmd())
    npages = extract["pages"]
    text_pages = [p["page"] for p in extract["page_infos"] if p["chars"] > 50] or [1]
    # 富文本页（字符数接近峰值）：避免把图页（坐标轴/图注短文本）当作章节证据来源
    chars_of = {p["page"]: p["chars"] for p in extract["page_infos"]}
    max_chars = max((chars_of.get(p, 0) for p in text_pages), default=1) or 1
    rich_pages = [p for p in text_pages if chars_of.get(p, 0) >= 0.6 * max_chars] or text_pages
    inv = read_json(os.path.join(ctx.work, "inputs_inventory.json"), default={})

    title_line = _pick_line(ctx, text_pages[0]) or "(论文标题待填)"
    # 结果数字候选：剔除章节标题样式（"1. Introduction"），优先含 % 的信息行
    cands = [c for c in extract.get("num_candidates", [])
             if not re.match(r"^\d+\.[\d.]*\s+[A-Z\u4e00-\u9fff]", c["line"])]
    cands.sort(key=lambda c: (0 if "%" in c["line"] else 1, -len(c["line"])))
    num_lines = cands[:6]
    figs = extract.get("figures", [])

    def page_anchor(pno, quote):
        return {"type": "page", "ref": f"p.{pno}", "quote": quote[:220]}

    slides = []
    slides.append({
        "kind": "title", "title": title_line[:90], "claim": "",
        "bullets": [], "figures": [],
        "evidence": [page_anchor(text_pages[0], title_line)],
        "notes": "", "layout_hint": "Title Slide",
    })
    bg_line = _pick_line(ctx, text_pages[0], prefer=("abstract", "摘要", "we ", "本文")) or title_line
    slides.append({
        "kind": "background", "title": "Background / 研究背景", "claim": "",
        "bullets": [bg_line[:200]], "figures": [],
        "evidence": [page_anchor(text_pages[0], bg_line)],
        "notes": "", "layout_hint": "Title and Content",
    })
    mpage = rich_pages[1] if len(rich_pages) > 1 else rich_pages[0]
    m_line = _pick_line(ctx, mpage, prefer=("method", "方法", "dataset", "数据")) or "方法要点待提炼"
    slides.append({
        "kind": "method", "title": "Method / 方法", "claim": "",
        "bullets": [m_line[:200]], "figures": [],
        "evidence": [page_anchor(mpage, m_line)],
        "notes": "", "layout_hint": "Title and Content",
    })
    res_bullets = [c["line"][:200] for c in num_lines[:4]] or ["结果数字待从原文摘录（必须逐字）"]
    res_ev = [page_anchor(c["page"], c["line"]) for c in num_lines[:4]] or [page_anchor(mpage, m_line)]
    res_figs = []
    for fg in figs[:2]:
        res_figs.append({"ref": fg["label"], "path": fg["path"],
                         "caption": f"{fg['label']}（源 p.{fg['page']}，{fg['source']}）"})
    slides.append({
        "kind": "results", "title": "Results / 结果", "claim": "",
        "bullets": res_bullets, "figures": res_figs,
        "evidence": res_ev + [{"type": "figure", "ref": fg["label"], "quote": ""} for fg in figs[:2]],
        "notes": "", "layout_hint": "Title and Content",
    })
    dpage, d_line = _pick_line_across(ctx, list(reversed(rich_pages)),
                                      ("limit", "discussion", "however", "局限", "trade-off", "future"))
    if not d_line:
        dpage = rich_pages[-2] if len(rich_pages) >= 2 else rich_pages[0]
        d_line = _pick_line(ctx, dpage) or "讨论要点待提炼"
    slides.append({
        "kind": "discussion", "title": "Discussion / 讨论与局限", "claim": "",
        "bullets": [d_line[:200]], "figures": [],
        "evidence": [page_anchor(dpage, d_line)],
        "notes": "", "layout_hint": "Title and Content",
    })
    cpage, c_line = _pick_line_across(ctx, list(reversed(rich_pages)),
                                      ("conclude", "conclusion", "结论", "released", "in summary"))
    if not c_line:
        cpage, c_line = rich_pages[-1], (_pick_line(ctx, rich_pages[-1]) or d_line)
    slides.append({
        "kind": "conclusion", "title": "Conclusion / 结论", "claim": "",
        "bullets": [c_line[:200]], "figures": [],
        "evidence": [page_anchor(cpage, c_line)],
        "notes": "", "layout_hint": "Title and Content",
    })

    plan = {
        "schema_version": "1.0",
        "mainline": {"problem": "", "method": "", "results": "", "limitations": ""},
        "audience": "学术同行（可由 Agent 依据 task.md 修正）",
        "duration_min": 12,
        "slides": slides,
        "meta": {
            "generated_by": "S4 plan-skeleton (prefill)",
            "source_pdf": extract["pdf"],
            "template": tpl["template"],
            "case_id": inv.get("case_id"),
            "note": "STOP：请 Agent 编辑本文件（提炼主线/主张/讲稿），数字必须与原文逐字一致，"
                    "每条 evidence.quote 必须是原文逐字片段。编辑后运行 finish。",
        },
    }
    plan_path = os.path.join(ctx.work, "slide_plan.json")
    if os.path.isfile(plan_path):
        old_sha = sha256_file(plan_path)
        ck = read_json(ctx.ckpt_path("S4"), default={}) or {}
        if old_sha != ck.get("prefilled_sha"):
            bak = plan_path + ".backup-" + now_iso().replace(":", "-")
            write_json(bak, read_json(plan_path, default={}))
            print(f"[S4] 检测到已编辑的旧 plan，备份到 {bak} 后重新预填", flush=True)
    write_json(plan_path, plan)
    return [plan_path]


# ---------------------------------------------------------------- S8


def stage_S8(ctx: Ctx):
    """QA 门禁汇总：六个机器门禁，overall = 最差门禁。"""
    inv = read_json(os.path.join(ctx.work, "inputs_inventory.json"), default={})
    fields = (inv or {}).get("output_contract_fields") or []
    result = read_json(ctx.result_path(), default={}) or {}
    missing = [f for f in fields if f not in result]
    if "case_id" not in result:
        missing.append("case_id")
    sm.save_gate(ctx, "contract-fields-present",
                 "fail" if missing else "pass",
                 ctx.result_path(),
                 "result.json 含全部 contract 字段" if not missing
                 else f"缺字段: {missing}")

    pg = read_json(os.path.join(ctx.gates_dir, "plan_gate.json"), default=None)
    if not pg:
        raise StageFailure("缺少 S5 plan-gate 记录", hint=ctx.default_resume_cmd())
    for g in ("evidence-anchors-resolve", "numbers-verbatim-vs-source"):
        info = pg["gates"][g]
        sm.save_gate(ctx, g, info["status"], os.path.join(ctx.gates_dir, "plan_gate.json"),
                     info.get("detail", ""))

    br = read_json(os.path.join(ctx.work, "build_report.json"), default=None)
    if not br:
        raise StageFailure("缺少 S6 build_report.json", hint=ctx.default_resume_cmd())
    n_fb = len(br.get("fallbacks", []))
    wrong_layout = [s for s in br.get("slides", [])
                    if s.get("layout") not in (br.get("template_layout_names") or [])]
    if wrong_layout:
        sm.save_gate(ctx, "template-layouts-used", "fail", os.path.join(ctx.work, "build_report.json"),
                     f"{len(wrong_layout)} 页未使用模板版式")
    elif n_fb:
        sm.save_gate(ctx, "template-layouts-used", "degraded", os.path.join(ctx.work, "build_report.json"),
                     f"全部页使用模板版式；{n_fb} 处占位符缺失改用 textbox 兜底（已记录）")
    else:
        sm.save_gate(ctx, "template-layouts-used", "pass", os.path.join(ctx.work, "build_report.json"),
                     f"{len(br.get('slides', []))} 页全部基于模板版式构建，占位符命中")

    er = read_json(os.path.join(ctx.work, "export_report.json"), default=None)
    if not er:
        raise StageFailure("缺少 S7 export_report.json", hint=ctx.default_resume_cmd())
    if er.get("pdf_pages") is None:
        sm.save_gate(ctx, "export-page-parity", "degraded", os.path.join(ctx.work, "export_report.json"),
                     "无可用渲染器（soffice 缺失），PDF 未导出；页数一致性无法核验")
    elif er.get("parity"):
        sm.save_gate(ctx, "export-page-parity", "pass", os.path.join(ctx.work, "export_report.json"),
                     f"pptx {er['pptx_slides']} 页 == pdf {er['pdf_pages']} 页")
    else:
        sm.save_gate(ctx, "export-page-parity", "fail", os.path.join(ctx.work, "export_report.json"),
                     f"页数不一致: pptx {er.get('pptx_slides')} vs pdf {er.get('pdf_pages')}")
    pc = er.get("preview_count", 0)
    if er.get("pdf_pages") and pc == er["pdf_pages"]:
        detail = f"{pc} 页 PNG 预览与 PDF 页数一致（渲染器: {er.get('renderer')}）"
        st = "pass" if er.get("renderer", "").startswith("soffice+pdftoppm") else "degraded"
        if st == "degraded":
            detail += "（使用了回退渲染路径）"
        sm.save_gate(ctx, "preview-pages-rendered", st, os.path.join(ctx.work, "export_report.json"), detail)
    elif pc > 0:
        sm.save_gate(ctx, "preview-pages-rendered", "degraded", os.path.join(ctx.work, "export_report.json"),
                     f"仅渲染 {pc} 页预览")
    else:
        st = "degraded" if er.get("pdf_pages") is None else "fail"
        sm.save_gate(ctx, "preview-pages-rendered", st, os.path.join(ctx.work, "export_report.json"),
                     "未生成任何 PNG 预览")

    gates = read_json(ctx.qa_gates_path(), default={})
    write_json(os.path.join(ctx.gates_dir, "qa_gates.json"), gates)
    degraded = [g for g in gates.get("gates", []) if g["status"] != "pass"]
    if degraded:
        sm.update_result(ctx, add_uncertainty=[
            f"QA 门禁 {g['gate']}={g['status']}: {g.get('detail', '')}" for g in degraded
        ])
    sm.update_result(ctx, append_log={"stage": "S8", "at": now_iso(),
                                      "note": f"qa-gate overall={gates.get('overall')}"})
    return [ctx.qa_gates_path(), os.path.join(ctx.gates_dir, "qa_gates.json")]


# ---------------------------------------------------------------- S9


def stage_S9(ctx: Ctx):
    """finalize：写齐 result.json（终态）、打印逐页核对清单。"""
    gates = read_json(ctx.qa_gates_path(), default={}) or {}
    overall = gates.get("overall", "fail")
    plan = read_json(os.path.join(ctx.work, "slide_plan.json"), default={}) or {}
    br = read_json(os.path.join(ctx.work, "build_report.json"), default={}) or {}
    er = read_json(os.path.join(ctx.work, "export_report.json"), default={}) or {}

    deck = os.path.join(ctx.output, "deck.pptx")
    if overall == "pass" and os.path.isfile(deck):
        status = "success"
    elif os.path.isfile(deck):
        status = "partial"
    else:
        status = "failed"

    artifacts = []
    for root, _dirs, files in os.walk(ctx.output):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ctx.output)
            if rel in ("result.json", "pipeline_manifest.json"):
                continue
            artifacts.append({"path": rel, "sha256": sha256_file(p), "bytes": os.path.getsize(p)})
    evidence_map = []
    for i, s in enumerate(plan.get("slides", [])):
        evidence_map.append({
            "slide": i + 1, "kind": s.get("kind"), "title": s.get("title"),
            "claim": s.get("claim", ""),
            "figures": [f.get("ref") for f in s.get("figures", [])],
            "evidence": s.get("evidence", []),
        })
    n_pass = sum(1 for g in gates.get("gates", []) if g["status"] == "pass")
    n_all = len(gates.get("gates", []))
    summary = (f"{len(plan.get('slides', []))} 页学术汇报已按模板构建（deck.pptx），"
               f"机器门禁 {n_pass}/{n_all} 通过，overall={overall}。"
               + ("" if status == "success" else "存在 degraded/fail 门禁，详见 qa_gates.json 与 uncertainty。"))
    patch = {
        "status": status,
        "summary": summary,
        "artifacts": artifacts,
        "evidence_map": evidence_map,
    }
    sm.update_result(ctx, patch=patch,
                     clear_uncertainty_prefix="S2-S9 尚未完成",
                     append_log={"stage": "S9", "at": now_iso(),
                                 "note": f"finalize: status={status}, gates overall={overall}"})
    result = read_json(ctx.result_path(), default={}) or {}
    if status != "success":
        unc = result.get("uncertainty", [])
        if isinstance(unc, list) and not any("最终状态" in str(u) for u in unc):
            unc.append(f"最终状态 {status}：未通过全部门禁即不交付 success，"
                       "缺失项见 qa_gates.json。")
            write_json(ctx.result_path(), result)

    print("---- 逐页核对清单 ----", flush=True)
    for i, s in enumerate(br.get("slides", [])):
        print(f"  p{i+1} [{s.get('layout')}] {str(s.get('title'))[:40]} "
              f"| evidence={s.get('n_evidence', 0)} figures={s.get('n_figures', 0)} "
              f"| body={s.get('body_via')}", flush=True)
    print(f"---- gates overall={overall}; deck.pdf pages={er.get('pdf_pages')}; "
          f"previews={er.get('preview_count')} ----", flush=True)
    return [ctx.result_path(), ctx.manifest_path()]


# ---------------------------------------------------------------- 阶段机装配

def _stage_inputs(ctx: Ctx, sid: str):
    w = ctx.work
    table = {
        "S0": [],
        "S1": [os.path.join(ctx.input_dir, f) for f in _list_input_files(ctx)],
        "S2": [os.path.join(w, "inputs_inventory.json")],
        "S3": [os.path.join(w, "inputs_inventory.json")],
        "S4": [os.path.join(w, "paper", "extract.json"), os.path.join(w, "template_report.json")],
        "S5": [os.path.join(w, "slide_plan.json"), os.path.join(w, "paper", "extract.json")],
        "S6": [os.path.join(w, "slide_plan.json"), os.path.join(w, "gates", "plan_gate.json"),
               os.path.join(w, "template_report.json")],
        "S7": [os.path.join(ctx.output, "deck.pptx"), os.path.join(w, "build_report.json")],
        "S8": [os.path.join(w, "gates", "plan_gate.json"), os.path.join(w, "build_report.json"),
               os.path.join(w, "export_report.json")],
        "S9": [os.path.join(w, "gates", "qa_gates.json"), os.path.join(w, "build_report.json"),
               os.path.join(w, "export_report.json")],
    }
    return table[sid]


def _list_input_files(ctx: Ctx):
    out = []
    for root, _dirs, names in os.walk(ctx.input_dir):
        for fn in sorted(names):
            out.append(os.path.relpath(os.path.join(root, fn), ctx.input_dir))
    return sorted(out)


def run_pipeline(ctx: Ctx, stop_after: str | None = None):
    import plan_gate
    import build_stage
    import export_stage
    funcs = {
        "S0": stage_S0, "S1": stage_S1, "S2": stage_S2, "S3": stage_S3, "S4": stage_S4,
        "S5": plan_gate.run, "S6": build_stage.run, "S7": export_stage.run,
        "S8": stage_S8, "S9": stage_S9,
    }
    for sid, name in sm.STAGES:
        inputs = _stage_inputs(ctx, sid)
        if ctx.skip_if_valid(sid, inputs):
            if sid == "S4":
                _enforce_plan_edited(ctx)
        else:
            t0 = time.time()
            try:
                outputs = funcs[sid](ctx)
            except StageFailure as e:
                ctx.fail(sid, name, e)
            except Exception as e:  # 未预期异常也要落检查点失败记录
                ctx.fail(sid, name, StageFailure(f"{type(e).__name__}: {e}"))
            extra = None
            if sid == "S4":
                extra = {"prefilled_sha": sha256_file(os.path.join(ctx.work, "slide_plan.json"))}
            ctx.complete(sid, name, inputs, outputs, time.time() - t0, extra=extra)
            sm.update_manifest(ctx)
            if sid == "S4":
                _enforce_plan_edited(ctx)
        if stop_after and sid == stop_after:
            break


def _enforce_plan_edited(ctx: Ctx):
    """finish 模式下：plan 必须已被 Agent 编辑过（否则 S4 预填骨架直接构建没有意义）。"""
    if ctx.command != "finish":
        return
    ck = read_json(ctx.ckpt_path("S4"), default={}) or {}
    plan_path = os.path.join(ctx.work, "slide_plan.json")
    if ck.get("prefilled_sha") and os.path.isfile(plan_path) \
            and sha256_file(plan_path) == ck["prefilled_sha"]:
        ctx.fail("S5", "plan-gate", StageFailure(
            "slide_plan.json 仍是 S4 预填骨架，尚未由 Agent 编辑",
            hint=(f"编辑 {plan_path}（提炼 mainline/claim/bullets/notes，数字逐字、证据可解析）后重跑："
                  f"{ctx.default_resume_cmd()}；合成演示可运行 "
                  f"python3 {ctx.skill_root}/scripts/fill_example_plan.py --work {ctx.work}")))


def cmd_status(ctx: Ctx) -> int:
    print("=== gated-pipeline-deck status ===", flush=True)
    result = read_json(ctx.result_path(), default={}) or {}
    print(f"case_id: {result.get('case_id', '(unknown)')}")
    next_stage = None
    for sid, name in sm.STAGES:
        ck = read_json(ctx.ckpt_path(sid))
        failed = read_json(ctx.failed_path(sid))
        if ck and ck.get("status") == "ok":
            row = f"{sid} {name:<18} ok       {ck.get('wall_time_s')}s  {ck.get('at')}"
        elif failed:
            row = f"{sid} {name:<18} FAILED   -  {failed.get('error', '')[:60]}"
            next_stage = next_stage or sid
        else:
            row = f"{sid} {name:<18} pending"
            next_stage = next_stage or sid
        print(row, flush=True)
    gates = read_json(ctx.qa_gates_path())
    if gates:
        line = " ".join(f"{g['gate']}={g['status']}" for g in gates.get("gates", []))
        print(f"gates: {line}")
        print(f"gates overall: {gates.get('overall')}")
    else:
        print("gates: (qa_gates.json 尚未生成)")
    if result:
        print(f"result.json: status={result.get('status')} artifacts={len(result.get('artifacts') or [])}")
    else:
        print("result.json: (尚未生成，先跑 prepare)")
    if next_stage:
        cmd = (f"python3 {ctx.skill_root}/scripts/run_case.py prepare --input {ctx.input_dir} "
               f"--work {ctx.work} --output {ctx.output}") if next_stage <= "S4" else ctx.default_resume_cmd()
        print(f"next: 从 {next_stage} 续跑 -> {cmd}")
    else:
        print("next: 全部阶段完成")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="run_case.py", description="gated-pipeline-deck 阶段机")
    ap.add_argument("command", choices=["prepare", "finish", "status"])
    ap.add_argument("--input", required=True, help="输入目录（含 case.json/task.md/材料）")
    ap.add_argument("--work", required=True, help="工作目录 /app/work")
    ap.add_argument("--output", required=True, help="交付目录 /app/output")
    args = ap.parse_args(argv)
    ctx = Ctx(args.input, args.work, args.output, args.command)
    if args.command == "status":
        return cmd_status(ctx)
    if args.command == "prepare":
        run_pipeline(ctx, stop_after="S4")
        plan_path = os.path.join(ctx.work, "slide_plan.json")
        print("", flush=True)
        print("==== NEXT ACTION ====", flush=True)
        print(f"1. /app/output/result.json 已是诚实 partial（含全部 contract 字段）。", flush=True)
        print(f"2. 请编辑 {plan_path} ：提炼 mainline/每页 claim/bullets/notes；", flush=True)
        print(f"   数字必须与源文逐字一致，每条 evidence 必须能解析到抽取产物。", flush=True)
        print(f"3. 然后运行: {ctx.default_resume_cmd()}", flush=True)
        return 0
    run_pipeline(ctx, stop_after=None)
    gates = read_json(ctx.qa_gates_path(), default={}) or {}
    print(f"FINISH: gates overall={gates.get('overall')}; "
          f"result status={(read_json(ctx.result_path(), default={}) or {}).get('status')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
