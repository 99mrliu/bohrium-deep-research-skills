#!/usr/bin/env python3
"""fidelity_scan.py -- upstream source-fidelity forensics for paper notes.

Builds a line-anchored text layer (anchors ``p<page>-l<line>``) plus a
*fidelity receipt* that records how much of each page actually survived
extraction, which layout risks were detected and which lines were only
*flagged* (never silently deleted).  Notes written later anchor into this
verified layer; anything the layer cannot vouch for must be reported as a
limit, not summarized away.

Backends (probed in order, first success wins unless --backend is given):
  1. poppler ``pdftotext -bbox-layout``  -> words with coordinates, rebuilt
     into visual lines; two-column reading order via gutter detection.
  2. ``pdftotext`` plain text            -> no coordinates, column audit is
     marked unavailable instead of guessed.
  3. PyMuPDF (``import fitz``)           -> spans with coordinates.
  4. ``--text-file``                     -> trusted text export, pages split
     on form-feed characters.

Standard library only; external tools are probed, never assumed.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

VERSION = "1.0.0"
ANCHOR = "p{page}-l{line}"

KNOWN_HEADINGS = (
    "abstract", "introduction", "background", "related work", "methods",
    "method", "materials and methods", "methodology", "experiments",
    "experimental setup", "results", "results and discussion", "discussion",
    "conclusion", "conclusions", "limitations", "references",
    "acknowledgements", "acknowledgments", "appendix", "supplementary material",
)
NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+(\S.*)$")


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def norm_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------------------------------------------- backends
def poppler_bbox_pages(pdf_path, workdir):
    """Return pages as word lists with coordinates via pdftotext -bbox-layout."""
    out_html = os.path.join(workdir, "bbox.html")
    cmd = ["pdftotext", "-bbox-layout", pdf_path, out_html]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if proc.returncode != 0 or not os.path.exists(out_html):
        raise RuntimeError("pdftotext -bbox-layout failed: " + proc.stderr.strip()[:400])
    tree = ET.parse(out_html)
    root = tree.getroot()
    # poppler bbox output is XHTML with a default namespace; match by local name.
    # Reuse poppler's own flow/block/line hierarchy: lines are column-aware and
    # document order already is the layout reading order.
    def local(tag):
        return tag.rsplit("}", 1)[-1]
    pages = []
    for page_el in root.iter():
        if local(page_el.tag) != "page":
            continue
        width = float(page_el.attrib.get("width", 0) or 0)
        height = float(page_el.attrib.get("height", 0) or 0)
        lines = []
        for el in page_el.iter():
            if local(el.tag) != "line":
                continue
            words = [w.text or "" for w in el if local(w.tag) == "word"]
            text = norm_space(" ".join(words))
            if not text:
                continue
            lines.append({"x0": float(el.attrib["xMin"]), "y0": float(el.attrib["yMin"]),
                          "x1": float(el.attrib["xMax"]), "y1": float(el.attrib["yMax"]),
                          "text": text})
        pages.append({"width": width, "height": height, "lines": lines})
    if not pages:
        raise RuntimeError("bbox output contained no pages")
    return pages


def pymupdf_pages(pdf_path):
    import fitz  # optional dependency, probed
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        rect = page.rect
        mid = rect.width / 2.0
        blocks = []
        for x0, y0, x1, y1, text, *_rest in page.get_text("blocks"):
            for raw in (text or "").splitlines():
                t = norm_space(raw)
                if t:
                    blocks.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": t})
        spanning = [b for b in blocks if b["x0"] < mid * 0.86 and b["x1"] > mid * 1.14]
        if len(spanning) <= max(2, 0.15 * len(blocks)) and blocks:
            left = sorted([b for b in blocks if b not in spanning and b["x1"] <= mid + 12],
                          key=lambda b: (b["y0"], b["x0"]))
            right = sorted([b for b in blocks if b not in spanning and b["x1"] > mid + 12],
                           key=lambda b: (b["y0"], b["x0"]))
            top = [b for b in sorted(spanning, key=lambda b: b["y0"])
                   if not left or b["y0"] < left[0]["y0"]]
            rest = [b for b in spanning if b not in top]
            ordered = top + left + right + rest
        else:
            ordered = sorted(blocks, key=lambda b: (b["y0"], b["x0"]))
        pages.append({"width": rect.width, "height": rect.height, "lines": ordered})
    return pages


def poppler_plain_pages(pdf_path, workdir):
    out_txt = os.path.join(workdir, "plain.txt")
    proc = subprocess.run(["pdftotext", pdf_path, out_txt],
                          capture_output=True, text=True, timeout=240)
    if proc.returncode != 0:
        raise RuntimeError("pdftotext failed: " + proc.stderr.strip()[:400])
    with open(out_txt, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    return text_to_pages(raw)


def text_to_pages(raw):
    pages = []
    for chunk in raw.split("\f"):
        if chunk.strip() == "" and len(raw.split("\f")) > 1:
            continue
        pages.append({"width": 0.0, "height": 0.0,
                      "lines": [ln.rstrip() for ln in chunk.splitlines()]})
    return pages or [{"width": 0.0, "height": 0.0, "lines": []}]


# ------------------------------------------------------- geometry -> lines
def column_audit(lines, page_width):
    """Evidence-only audit of the line layout; ordering itself comes from the
    backend's own flow hierarchy (poppler) or block ordering (PyMuPDF)."""
    if page_width <= 0 or not lines:
        return {"two_column": None, "order": "backend order",
                "evidence": "no coordinates with this backend"}
    body = [ln for ln in lines if ln["x1"] - ln["x0"] > page_width * 0.06]
    span = [ln for ln in body if ln["x0"] < page_width * 0.42
            and ln["x1"] > page_width * 0.58]
    left = [ln for ln in body if ln["x1"] <= page_width * 0.52]
    right = [ln for ln in body if ln["x0"] >= page_width * 0.48]
    two_col = bool(len(body) >= 6 and len(span) <= 0.4 * len(body)
                   and len(left) >= 3 and len(right) >= 3)
    evidence = ("%d/%d lines span the midline; %d left / %d right lines"
                % (len(span), len(body), len(left), len(right)))
    order = ("column-major (top spanning lines, left column, right column, "
             "mid-page spanning lines last)" if two_col else
             "backend flow order; layout reads as single-column or mixed")
    return {"two_column": two_col, "order": order, "evidence": evidence}


def reorder_two_column(lines, page_width):
    """Deterministic column-major order: top spanning lines, then the left
    column top-to-bottom, then the right column, then mid-page spanning
    lines (wide figures/tables) last."""
    mid = page_width / 2.0
    m_top_band, m, left, right = [], [], [], []
    for ln in lines:
        if ln["x0"] < page_width * 0.42 and ln["x1"] > page_width * 0.58:
            m.append(ln)
        elif ln["x1"] <= mid + 12:
            left.append(ln)
        elif ln["x0"] >= mid - 12:
            right.append(ln)
        elif (ln["x0"] + ln["x1"]) / 2.0 < mid:
            left.append(ln)
        else:
            right.append(ln)
    left.sort(key=lambda l: (l["y0"], l["x0"]))
    right.sort(key=lambda l: (l["y0"], l["x0"]))
    m.sort(key=lambda l: (l["y0"], l["x0"]))
    heights = sorted(ln["y1"] - ln["y0"] for ln in lines if ln["y1"] > ln["y0"])
    line_h = heights[len(heights) // 2] if heights else 10.0
    # top zone = everything above the first y-band where left and right
    # columns coexist (title, authors, spanning abstract, wide headings)
    pair_y = None
    for l in left:
        for r in right:
            if abs(l["y0"] - r["y0"]) <= 1.5 * line_h:
                cand = min(l["y0"], r["y0"])
                pair_y = cand if pair_y is None else min(pair_y, cand)
    if pair_y is not None:
        top = sorted([ln for ln in lines if ln["y1"] <= pair_y + 0.3 * line_h],
                     key=lambda l: (l["y0"], l["x0"]))
        left = [ln for ln in left if ln not in top]
        right = [ln for ln in right if ln not in top]
        m_rest = [ln for ln in m if ln not in top]
    else:
        first_body_y = left[0]["y0"] if left else (right[0]["y0"] if right else 0)
        top = [ln for ln in m if ln["y0"] < first_body_y]
        m_rest = [ln for ln in m if ln["y0"] >= first_body_y]
    return top + left + right + m_rest


# -------------------------------------------------------------- diagnostics
def is_heading(text):
    t = norm_space(text)
    if not t or len(t) > 120:
        return None
    low = t.lower().strip(".: ")
    if low in KNOWN_HEADINGS:
        return t
    m = NUMBERED_HEADING.match(t)
    if m and (m.group(2)[0].isupper() or m.group(2).isupper()):
        return t
    return None


def build_sections(lines_with_anchor):
    sections = []
    refs_seen = False
    for item in lines_with_anchor:
        title = is_heading(item["text"])
        if not title:
            continue
        if refs_seen and NUMBERED_HEADING.match(title):
            continue  # numbered entries after REFERENCES are bibliography noise
        if title.lower().strip(".: ") == "references":
            refs_seen = True
        sections.append({"title": title, "anchor": item["anchor"]})
    return sections


def page_fidelity(page_index, lines, raw_line_count, backend):
    text = "\n".join(ln["text"] for ln in lines)
    chars = len(text)
    replacement = text.count("�")
    weird = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text))
    alnum = sum(c.isalnum() for c in text)
    ratio = (alnum / chars) if chars else 0.0
    flags = []
    if chars < 40:
        flags.append("page_nearly_empty_text_layer: possible scanned page")
    if replacement:
        flags.append("unicode_replacement_chars:%d" % replacement)
    if weird:
        flags.append("control_chars:%d" % weird)
    if chars >= 40 and ratio < 0.5:
        flags.append("low_alnum_ratio:%.2f possible encoding damage" % ratio)
    if backend == "poppler-bbox" and raw_line_count > 0 and not lines:
        flags.append("geometry_rebuild_lost_all_words")
    return {
        "page": page_index,
        "chars": chars,
        "alnum_ratio": round(ratio, 3),
        "lines": len(lines),
        "flags": flags,
    }


# -------------------------------------------------------------------- main
def scan(args):
    os.makedirs(args.out, exist_ok=True)
    diagnostics = {"backend": None, "backend_chain": [], "version": VERSION}
    pages_words = None
    pages_plain = None
    source_bytes = b""

    if args.text_file:
        with open(args.text_file, "rb") as fh:
            source_bytes = fh.read()
        pages_plain = text_to_pages(source_bytes.decode("utf-8", errors="replace"))
        diagnostics["backend"] = "text-file"
        diagnostics["note"] = "trusted text export; column audit unavailable"
    else:
        with open(args.pdf, "rb") as fh:
            source_bytes = fh.read()
        order = [args.backend] if args.backend else ["poppler-bbox", "pymupdf", "poppler-plain"]
        for backend in order:
            try:
                if backend == "poppler-bbox":
                    if not shutil.which("pdftotext"):
                        raise RuntimeError("pdftotext not on PATH")
                    pages_words = poppler_bbox_pages(args.pdf, args.out)
                elif backend == "pymupdf":
                    pages_words = pymupdf_pages(args.pdf)
                elif backend == "poppler-plain":
                    if not shutil.which("pdftotext"):
                        raise RuntimeError("pdftotext not on PATH")
                    pages_plain = poppler_plain_pages(args.pdf, args.out)
                else:
                    raise RuntimeError("unknown backend " + str(backend))
                diagnostics["backend"] = backend
                break
            except Exception as exc:  # probe failure is data, not a crash
                diagnostics["backend_chain"].append({"backend": backend, "error": str(exc)[:300]})
        if diagnostics["backend"] is None or not (pages_words or pages_plain):
            receipt = {
                "status": "unreadable",
                "reason": "no extraction backend produced usable text; PDF may be "
                          "scanned, encrypted or the runtime lacks pdftotext/PyMuPDF",
                "backend_chain": diagnostics["backend_chain"],
                "handover": "render/OCR the PDF with the platform tools, then rerun "
                            "with --text-file <ocr-export.txt>; do not invent content",
            }
            with open(os.path.join(args.out, "fidelity.json"), "w", encoding="utf-8") as fh:
                json.dump(receipt, fh, ensure_ascii=False, indent=2)
            print(json.dumps(receipt, ensure_ascii=False))
            return 3

    doc_id = args.case_id or "doc"
    source = {"doc_id": doc_id, "backend": diagnostics["backend"],
              "sha256": sha256_bytes(source_bytes), "pages": []}
    fidelity_pages = []
    all_lines = []

    for pno, page in enumerate(pages_words or pages_plain, start=1):
        if pages_words is not None:
            col_info = column_audit(page["lines"], page["width"])
            ordered = (reorder_two_column(page["lines"], page["width"])
                       if col_info["two_column"] else page["lines"])
            raw_count = len(page["lines"])
        else:
            ordered = [{"text": norm_space(t)} for t in page["lines"] if norm_space(t)]
            col_info = {"two_column": None, "order": "as-exported",
                        "evidence": "no coordinates with this backend"}
            raw_count = len(page["lines"])
        page_entry = {"page": pno, "columns": col_info, "lines": []}
        for lno, ln in enumerate(ordered, start=1):
            anchor = ANCHOR.format(page=pno, line=lno)
            page_entry["lines"].append({"anchor": anchor, "text": ln["text"]})
            all_lines.append({"anchor": anchor, "text": ln["text"]})
        source["pages"].append(page_entry)
        fidelity_pages.append(page_fidelity(pno, page_entry["lines"], raw_count,
                                            diagnostics["backend"]))

    sections = build_sections(all_lines)
    total_chars = sum(p["chars"] for p in fidelity_pages)
    empty_pages = [p["page"] for p in fidelity_pages if p["chars"] < 40]
    flagged = {str(p["page"]): p["flags"] for p in fidelity_pages if p["flags"]}

    fidelity = {
        "status": "degraded" if (empty_pages or flagged) else "ok",
        "doc_id": doc_id,
        "backend": diagnostics["backend"],
        "backend_chain": diagnostics["backend_chain"],
        "sha256": source["sha256"],
        "page_count": len(source["pages"]),
        "total_chars": total_chars,
        "empty_or_image_pages": empty_pages,
        "page_flags": flagged,
        "pages": fidelity_pages,
        "sections": sections,
        "limits": [
            "anchors are bound to this backend; re-scan after switching backends",
            "figure-internal text, formulas and table cell alignment are NOT "
            "guaranteed by the text layer; verify decisive values on the rendered page",
            "column detection is geometric; three-column or magazine layouts need review",
        ],
    }
    with open(os.path.join(args.out, "source.json"), "w", encoding="utf-8") as fh:
        json.dump(source, fh, ensure_ascii=False)
    with open(os.path.join(args.out, "fidelity.json"), "w", encoding="utf-8") as fh:
        json.dump(fidelity, fh, ensure_ascii=False, indent=2)
    atlas = ["# Line atlas (%s, backend=%s)" % (doc_id, diagnostics["backend"])]
    for page in source["pages"]:
        atlas.append("\n== page %d | columns: %s ==" % (page["page"], page["columns"]["order"]))
        for ln in page["lines"]:
            atlas.append("%s\t%s" % (ln["anchor"], ln["text"]))
    with open(os.path.join(args.out, "atlas.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(atlas) + "\n")
    print(json.dumps({"status": fidelity["status"], "backend": fidelity["backend"],
                      "pages": fidelity["page_count"], "chars": total_chars,
                      "sections": [s["title"] for s in sections]}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf")
    ap.add_argument("--text-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", default="doc")
    ap.add_argument("--backend", choices=["poppler-bbox", "pymupdf", "poppler-plain"])
    args = ap.parse_args()
    if not args.pdf and not args.text_file:
        ap.error("one of --pdf / --text-file is required")
    sys.exit(scan(args))


if __name__ == "__main__":
    main()
