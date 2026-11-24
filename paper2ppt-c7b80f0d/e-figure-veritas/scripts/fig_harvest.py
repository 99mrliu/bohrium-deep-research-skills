#!/usr/bin/env python3
"""fig_harvest.py — 论文 PDF 图表收割：先收割后写作的第一支柱。

功能：
  1. 嵌入位图抽取：pymupdf 优先 → pdfimages(subprocess) 降级 → 二者皆缺时
     honest tool_missing（不中断，caption 索引仍产出）。
  2. caption 索引：文本提取降级链 pdftotext(subprocess) → pymupdf → pypdf；
     匹配 "Figure N." / "Fig. N:" / "Table N." 开头的行作为 caption 原文。
  3. 引用绑定：全文中 "Fig. N" / "Figure N" 出现页与 caption 互相绑定。
  4. 有 caption 但本页无嵌入位图 → 整页渲染兜底（pymupdf 可用时），
     标注 extraction="page-render"；无法渲染则 extraction="missing"。

产物：--out-dir 下的图文件 + figure_manifest.json。
退出码：0 正常（含 tool_missing 降级）；2 参数/输入错误。
确定性：同输入同输出（manifest 不含时间戳）。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

CAP_FIG_RE = re.compile(r"^\s*(Figure|Fig\.?)\s+(\d+)\s*[.:]\s*(.+)$")
CAP_TAB_RE = re.compile(r"^\s*Table\s+(\d+)\s*[.:]\s*(.+)$")
REF_RE = re.compile(r"\b(?:Fig(?:ure)?\.?)\s*(\d+)\b")

SCHEMATIC_HINT = re.compile(
    r"\b(schematic|diagram|illustration|overview|workflow)\b", re.I)
DATA_HINT = re.compile(
    r"\b(measured|data|curve|spectrum|spectra|plot|response|results?|distribution|"
    r"histogram|intensity|profile)\b", re.I)


def kind_hint(caption):
    if SCHEMATIC_HINT.search(caption):
        return "schematic"
    if DATA_HINT.search(caption):
        return "data-figure"
    return "unknown"


# ---------- 文本提取降级链 ----------

def extract_pages_pdftotext(pdf_path):
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-layout", pdf_path, "-"],
                             capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    pages = out.stdout.decode("utf-8", "replace").split("\f")
    while pages and not pages[-1].strip():  # 末尾换页符产生的空元素
        pages.pop()
    return pages


def extract_pages_pymupdf(pdf_path):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # noqa: N813
        except ImportError:
            return None
    try:
        doc = pymupdf.open(pdf_path)
        pages = [page.get_text() for page in doc]
        doc.close()
        return pages
    except Exception:
        return None


def extract_pages_pypdf(pdf_path):
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        reader = PdfReader(pdf_path)
        return [(p.extract_text() or "") for p in reader.pages]
    except Exception:
        return None


def extract_text_pages(pdf_path):
    """返回 (pages_text, engine)；全部失败返回 ([], 'none')。"""
    pages = extract_pages_pdftotext(pdf_path)
    if pages:
        return pages, "pdftotext"
    pages = extract_pages_pymupdf(pdf_path)
    if pages:
        return pages, "pymupdf"
    pages = extract_pages_pypdf(pdf_path)
    if pages:
        return pages, "pypdf"
    return [], "none"


# ---------- 位图抽取 ----------

def extract_images_pymupdf(pdf_path, out_dir):
    """返回 {page_1based: [file,...]}；pymupdf 不可用返回 None。"""
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # noqa: N813
        except ImportError:
            return None
    result = {}
    try:
        doc = pymupdf.open(pdf_path)
    except Exception as exc:
        sys.stderr.write(f"error: cannot open PDF with pymupdf: {exc}\n")
        return None
    for pno in range(len(doc)):
        page = doc[pno]
        files = []
        seen = set()
        # get_image_info：只算真正绘制在本页的位图（get_images 会把共享资源
        # 字典里未被绘制的 XObject 也列出来，造成误判）
        try:
            infos = page.get_image_info(xrefs=True)
        except TypeError:
            infos = page.get_image_info()
        for info in infos:
            xref = info.get("xref", 0)
            if not xref or xref in seen:
                continue
            seen.add(xref)
            try:
                blob = doc.extract_image(xref)
            except Exception:
                continue
            ext = blob.get("ext", "png")
            fn = os.path.join(out_dir, f"embedded_p{pno + 1}_x{xref}.{ext}")
            with open(fn, "wb") as fh:
                fh.write(blob["image"])
            files.append(fn)
        if files:
            result[pno + 1] = files
    n_pages = len(doc)
    doc.close()
    result["_n_pages"] = n_pages
    return result


def render_page_png(pdf_path, page_1based, out_png, dpi=150):
    try:
        import pymupdf
    except ImportError:
        try:
            import fitz as pymupdf  # noqa: N813
        except ImportError:
            return False
    try:
        doc = pymupdf.open(pdf_path)
        page = doc[page_1based - 1]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        pix.save(out_png)
        doc.close()
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(
        description="Harvest figures/tables/captions from a paper PDF into a manifest.")
    ap.add_argument("pdf", help="paper.pdf")
    ap.add_argument("--out-dir", default="figs", help="directory for extracted images")
    ap.add_argument("--manifest", default="figure_manifest.json")
    args = ap.parse_args()

    if not os.path.isfile(args.pdf):
        sys.stderr.write(f"error: input PDF not found: {args.pdf}\n")
        return 2
    os.makedirs(args.out_dir, exist_ok=True)

    warnings = []
    pages_text, text_engine = extract_text_pages(args.pdf)
    if text_engine == "none":
        warnings.append("tool_missing: no PDF text extractor "
                        "(pdftotext/pymupdf/pypdf) available; captions not indexed")

    images = extract_images_pymupdf(args.pdf, args.out_dir)
    img_engine = "pymupdf"
    if images is None:
        images = {}
        if shutil.which("pdfimages"):
            img_engine = "pdfimages"
            warnings.append("pymupdf unavailable; pdfimages fallback not wired for "
                            "per-page mapping in this build; page-render used instead")
        else:
            img_engine = "none"
            warnings.append("tool_missing: neither pymupdf nor pdfimages available; "
                            "embedded bitmap extraction skipped")

    # caption 索引
    figures, tables = [], []
    for pno, text in enumerate(pages_text, start=1):
        if not text:
            continue
        for line in text.splitlines():
            m = CAP_FIG_RE.match(line)
            if m:
                num = int(m.group(2))
                caption = m.group(3).strip()
                figures.append({
                    "id": f"fig{num}",
                    "label": f"Figure {num}",
                    "page": pno,
                    "caption": caption,
                    "kind_hint": kind_hint(caption),
                    "refs_in_text": [],
                    "extraction": "missing",
                    "file": None,
                })
                continue
            m = CAP_TAB_RE.match(line)
            if m:
                num = int(m.group(1))
                tables.append({
                    "id": f"table{num}",
                    "label": f"Table {num}",
                    "page": pno,
                    "caption": m.group(2).strip(),
                    "refs_in_text": [],
                })

    # 去重（同号 caption 只保留首次出现）
    seen_fig, uniq_figures = set(), []
    for f in figures:
        if f["id"] not in seen_fig:
            seen_fig.add(f["id"])
            uniq_figures.append(f)
    figures = uniq_figures

    # 引用绑定
    for pno, text in enumerate(pages_text, start=1):
        if not text:
            continue
        for line in text.splitlines():
            if CAP_FIG_RE.match(line) or CAP_TAB_RE.match(line):
                continue
            for m in REF_RE.finditer(line):
                fid = f"fig{int(m.group(1))}"
                for f in figures:
                    if f["id"] == fid:
                        f["refs_in_text"].append({"page": pno,
                                                  "snippet": line.strip()[:120]})

    # 图文件归属：同页最大嵌入位图；否则整页渲染兜底
    for f in figures:
        page_imgs = images.get(f["page"], [])
        if page_imgs:
            biggest = max(page_imgs, key=lambda p: os.path.getsize(p))
            f["extraction"] = "embedded-bitmap"
            f["file"] = biggest
        else:
            out_png = os.path.join(args.out_dir, f"{f['id']}_p{f['page']}_page.png")
            if render_page_png(args.pdf, f["page"], out_png):
                f["extraction"] = "page-render"
                f["file"] = out_png
                warnings.append(f"{f['id']}: no embedded bitmap on page {f['page']}; "
                                f"whole-page render used (vector or flattened figure)")
            else:
                warnings.append(f"{f['id']}: no image extractable and page render "
                                f"unavailable (tool_missing)")

    manifest = {
        "source_pdf": os.path.abspath(args.pdf),
        "text_engine": text_engine,
        "image_engine": img_engine,
        "generated_by": "fig_harvest.py",
        "n_pages": len(pages_text),
        "figures": figures,
        "tables": tables,
        "warnings": warnings,
    }
    with open(args.manifest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"figures={len(figures)} tables={len(tables)} "
          f"text_engine={text_engine} image_engine={img_engine} "
          f"warnings={len(warnings)} -> {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
