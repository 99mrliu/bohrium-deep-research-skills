"""narrative-first-deck 共享工具。

纯 stdlib；PyMuPDF/python-pptx/pillow 由 bootstrap_deps() 保证可用后才被调用方 import。
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p, obj) -> None:
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_text(p, default="") -> str:
    p = Path(p)
    if not p.exists():
        return default
    return p.read_text(encoding="utf-8", errors="replace")


def sha256_file(p) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def eprint(*a):
    print(*a, file=sys.stderr)


REQUIRED_PY = [("pptx", "python-pptx"), ("fitz", "PyMuPDF"), ("PIL", "pillow")]


def bootstrap_deps(change_log: list) -> list:
    """确保 python-pptx / PyMuPDF / pillow 可用；缺失则 pip 安装。返回 degraded 说明列表。"""
    degraded = []
    for mod, pkg in REQUIRED_PY:
        try:
            __import__(mod)
        except ImportError:
            try:
                subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", pkg],
                               check=True, timeout=300)
                __import__(mod)
                change_log.append({"ts": now_iso(), "event": f"bootstrap: pip install {pkg}"})
            except Exception as e:  # noqa: BLE001
                degraded.append(f"python 依赖 {pkg} 缺失且自动安装失败: {e}")
    return degraded


def parse_task_constraints(task_text: str) -> dict:
    """从 task.md 文本解析 audience / duration_min / slides 范围。解析不到则对应字段为 None。"""
    out = {"audience": None, "duration_min": None, "slides_min": None, "slides_max": None}
    m = re.search(r"audience\s*[:：]\s*([^\n;；]+)", task_text, re.I)
    if m:
        out["audience"] = m.group(1).strip()
    m = re.search(r"(?:duration|时长)\s*[:：]\s*(\d+)\s*(?:min(?:utes)?|分钟)?", task_text, re.I)
    if not m:
        m = re.search(r"(\d+)\s*(?:分钟|minutes?)\b", task_text, re.I)
    if m:
        out["duration_min"] = int(m.group(1))
    m = re.search(r"slides\s*[:：]\s*(\d+)\s*[-–~]\s*(\d+)", task_text, re.I)
    if m:
        out["slides_min"], out["slides_max"] = int(m.group(1)), int(m.group(2))
    return out


def find_materials(input_dir, case: dict) -> dict:
    """在 /input 中发现论文 PDF 与模板 PPTX。优先 case.json 显式声明的路径。"""
    input_dir = Path(input_dir)
    found = {"paper_pdf": None, "template_pptx": None, "other": []}
    declared = []
    for key in ("materials", "files", "inputs", "resources"):
        v = case.get(key)
        if isinstance(v, list):
            declared += [str(x.get("path", x)) if isinstance(x, dict) else str(x) for x in v]
        elif isinstance(v, str):
            declared.append(v)
    pdfs, pptxs = [], []
    for d in declared:
        p = Path(d)
        if not p.is_absolute():
            p = input_dir / d
        if p.suffix.lower() == ".pdf" and p.exists():
            pdfs.append(p)
        elif p.suffix.lower() in (".pptx", ".ppt") and p.exists():
            pptxs.append(p)
    if not pdfs:
        pdfs = sorted(input_dir.rglob("*.pdf"))
    if not pptxs:
        pptxs = sorted(input_dir.rglob("*.pptx")) + sorted(input_dir.rglob("*.ppt"))
    if pdfs:
        found["paper_pdf"] = str(pdfs[0])
    if pptxs:
        found["template_pptx"] = str(pptxs[0])
    found["other"] = [str(p) for p in (pdfs[1:] + pptxs[1:])]
    return found


def extract_paper(pdf_path, work_dir) -> dict:
    """PyMuPDF 抽取论文：逐页文本、Figure/Table 标题、图片（无内嵌图则整页渲染兜底）、含数字句子候选。

    写出:
      work/paper/full_text.txt       全部页面文本（带 p.N 分隔）
      work/paper/figs/*.png          抽取/渲染的图
      work/paper/source_index.json   证据锚点索引（lint 与填 plan 的事实来源）
    """
    import fitz  # PyMuPDF，bootstrap 之后可用

    work_dir = Path(work_dir)
    paper_dir = work_dir / "paper"
    figs_dir = paper_dir / "figs"
    figs_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    pages, figures, tables, number_candidates = [], [], [], []
    full_chunks = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        pno = i + 1
        text = page.get_text("text") or ""
        full_chunks.append(f"\n===== p.{pno} =====\n{text}")
        fig_caps = re.findall(r"Figure\s*(\d+)\s*[:：]\s*([^\n]*)", text, re.I)
        tab_caps = re.findall(r"Table\s*(\d+)\s*[:：]\s*([^\n]*)", text, re.I)

        saved_imgs = []
        for j, img in enumerate(page.get_images(full=True)):
            try:
                pix = fitz.Pixmap(doc, img[0])
                if pix.n - pix.alpha > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                fn = f"p{pno}_img{j + 1}.png"
                pix.save(str(figs_dir / fn))
                saved_imgs.append(fn)
            except Exception:  # noqa: BLE001
                continue

        for k, (num, cap) in enumerate(fig_caps):
            label = f"Figure {num}"
            if k < len(saved_imgs):
                fn = saved_imgs[k]
            elif len(fig_caps) == 1 and saved_imgs:
                fn = saved_imgs[0]
            else:
                # 无可用内嵌图（如矢量图）：整页渲染兜底，保证锚点可解析、可上页
                fn = f"p{pno}_fig{num}.png"
                page.get_pixmap(dpi=150).save(str(figs_dir / fn))
            figures.append({"label": label, "page": pno,
                            "path": str(figs_dir / fn), "caption": cap.strip()})
        for num, cap in tab_caps:
            tables.append({"label": f"Table {num}", "page": pno, "caption": cap.strip()})

        for sent in re.split(r"(?<=[。！？.!?\n])", text):
            s = sent.strip()
            if s and re.search(r"\d", s) and len(s) <= 200:
                number_candidates.append({"page": pno, "text": s})
        pages.append({"page": pno, "n_chars": len(text), "head": text[:300]})

    full_text = "".join(full_chunks)
    (paper_dir / "full_text.txt").write_text(full_text, encoding="utf-8")
    index = {
        "source_pdf": str(pdf_path),
        "n_pages": doc.page_count,
        "pages": pages,
        "figures": figures,
        "tables": tables,
        "number_candidates": number_candidates[:80],
        "full_text_path": str(paper_dir / "full_text.txt"),
        "extracted_at": now_iso(),
    }
    write_json(paper_dir / "source_index.json", index)
    doc.close()
    return index


def template_anatomy(pptx_path) -> dict:
    """解剖模板：列出版式与占位符，供 build 时按名选择。"""
    from pptx import Presentation

    prs = Presentation(str(pptx_path))
    layouts = []
    for lay in prs.slide_layouts:
        phs = [{"idx": ph.placeholder_format.idx, "type": str(ph.placeholder_format.type),
                "name": ph.name} for ph in lay.placeholders]
        layouts.append({"name": lay.name, "placeholders": phs})
    return {"template": str(pptx_path),
            "slide_size_emu": [prs.slide_width, prs.slide_height],
            "n_layouts": len(layouts), "layouts": layouts}
