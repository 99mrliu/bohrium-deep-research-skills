"""extract_source.py — build the SOURCE CORPUS LEDGER from a paper PDF.

Outputs (under <work>/corpus/):
  corpus.jsonl   one JSON object per line:
      {"kind":"text",    "id":"p2-b3", "page":2, "bbox":[...], "text":"...",
       "sha256":"...", "numbers":[{"raw","core","unit"}...]}
      {"kind":"section", "id":"sec-2", "page":2, "heading":"Methods", ...}
      {"kind":"figure",  "fig_id":"fig-p5-1", "page":5, "bbox":[...],
       "label":"Figure 1", "file":"figs/fig-p5-1.png", "sha256":"..."}
  figs/          figure PNGs (embedded images, or rendered page regions for
                 vector figures located via their "Figure N" caption).

Every entry is hashed at extraction time. Downstream stages must reference
ledger entries, never re-extract or re-render silently.

Usage:
  python3 extract_source.py --pdf /path/paper.pdf --out /app/work/corpus
"""
from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

SECTION_RE = re.compile(
    r"^(abstract|introduction|background|related work|methods?|methodology|"
    r"materials and methods|experiments?|results?|discussion|conclusions?|"
    r"limitations?|references|acknowledg?ements?|appendix)\b", re.IGNORECASE)
NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z ,-]{2,60}$")
FIG_CAPTION_RE = re.compile(r"^(figure|fig\.?)\s*(\d+)", re.IGNORECASE)


def _block_is_heading(text: str, max_size: float, body_size: float) -> bool:
    t = text.strip()
    if not t or len(t) > 90:
        return False
    if SECTION_RE.match(t):
        return True
    if NUMBERED_HEADING_RE.match(t):
        return True
    # short line set in a clearly larger font → probable heading
    return len(t) < 70 and max_size >= body_size * 1.25


def extract(pdf_path: str, out_dir: str) -> dict:
    import pymupdf  # PyMuPDF

    figs_dir = os.path.join(out_dir, "figs")
    os.makedirs(figs_dir, exist_ok=True)
    corpus_path = os.path.join(out_dir, "corpus.jsonl")

    doc = pymupdf.open(pdf_path)
    entries: list[dict] = []
    fig_count = 0

    # first pass: estimate body font size for heading heuristic
    sizes = []
    for page in doc:
        for b in page.get_text("dict").get("blocks", []):
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        sizes.append(span.get("size", 10))
    body_size = sorted(sizes)[len(sizes) // 2] if sizes else 10.0

    sec_count = 0
    for pno in range(doc.page_count):
        page = doc[pno]
        page_no = pno + 1
        blocks = page.get_text("blocks")
        captions = []  # (bbox, label) for figure captions on this page

        for bno, blk in enumerate(blocks):
            x0, y0, x1, y1, text = blk[0], blk[1], blk[2], blk[3], blk[4]
            text = (text or "").strip()
            if not text:
                continue
            # max span size inside this block (for heading heuristic)
            max_size = body_size
            entry_id = f"p{page_no}-b{bno}"
            norm = common.norm_ws(text)
            entries.append({
                "kind": "text", "id": entry_id, "page": page_no,
                "bbox": [round(v, 2) for v in (x0, y0, x1, y1)],
                "text": norm, "sha256": common.sha256_text(norm),
                "numbers": common.extract_number_tokens(norm),
            })
            m = FIG_CAPTION_RE.match(norm)
            if m:
                captions.append(((x0, y0, x1, y1), f"Figure {m.group(2)}"))
            if _block_is_heading(norm, max_size, body_size):
                sec_count += 1
                entries.append({
                    "kind": "section", "id": f"sec-{sec_count}",
                    "page": page_no, "heading": norm,
                    "sha256": common.sha256_text(norm),
                })

        # --- figures: (1) embedded raster images --------------------------
        seen_xrefs = set()
        for img in page.get_images(full=True):
            xref = img[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)
            try:
                pix = pymupdf.Pixmap(doc, xref)
                if pix.n - pix.alpha > 3:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                if pix.width < 40 or pix.height < 40:
                    continue  # icons / artifacts, not figures
                fig_count += 1
                fig_id = f"fig-p{page_no}-{fig_count}"
                fname = f"{fig_id}.png"
                fpath = os.path.join(figs_dir, fname)
                pix.save(fpath)
                rects = page.get_image_rects(xref)
                bbox = [round(v, 2) for v in rects[0]] if rects else None
                entries.append({
                    "kind": "figure", "fig_id": fig_id, "page": page_no,
                    "bbox": bbox, "label": None,
                    "file": f"figs/{fname}", "sha256": common.sha256_file(fpath),
                })
            except Exception:  # noqa: BLE001
                continue

        # --- figures: (2) vector figures via caption region render --------
        for (cbbox, label) in captions:
            # render the area above the caption (or whole page minus margins)
            page_rect = page.rect
            clip = pymupdf.Rect(page_rect.x0 + 20, page_rect.y0 + 40,
                                page_rect.x1 - 20, max(cbbox[1] - 4,
                                                       page_rect.y0 + 120))
            # skip if an embedded image already covers this region
            covered = False
            for e in entries:
                if e.get("kind") == "figure" and e.get("page") == page_no and e.get("bbox"):
                    ex = pymupdf.Rect(e["bbox"])
                    if ex.intersects(clip) and ex.get_area() > 0.5 * clip.get_area():
                        covered = True
                        if not e.get("label"):
                            e["label"] = label
                        break
            if covered:
                continue
            fig_count += 1
            fig_id = f"fig-p{page_no}-{fig_count}"
            fname = f"{fig_id}.png"
            fpath = os.path.join(figs_dir, fname)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip)
            pix.save(fpath)
            entries.append({
                "kind": "figure", "fig_id": fig_id, "page": page_no,
                "bbox": [round(v, 2) for v in clip], "label": label,
                "file": f"figs/{fname}", "sha256": common.sha256_file(fpath),
            })

    doc.close()
    import json as _json
    with open(corpus_path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(_json.dumps(e, ensure_ascii=False) + "\n")

    stats = {
        "pdf": os.path.abspath(pdf_path),
        "pdf_sha256": common.sha256_file(pdf_path),
        "pages": len({e["page"] for e in entries if "page" in e}),
        "text_blocks": sum(1 for e in entries if e["kind"] == "text"),
        "sections": [e["heading"] for e in entries if e["kind"] == "section"],
        "figures": [{"fig_id": e["fig_id"], "page": e["page"],
                     "label": e.get("label"), "file": e["file"]}
                    for e in entries if e["kind"] == "figure"],
        "corpus": corpus_path,
    }
    common.dump_json(stats, os.path.join(out_dir, "corpus_meta.json"))
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    stats = extract(args.pdf, args.out)
    print(f"[extract_source] pages={stats['pages']} "
          f"text_blocks={stats['text_blocks']} "
          f"figures={len(stats['figures'])} "
          f"sections={len(stats['sections'])}")
    print(f"[extract_source] corpus -> {stats['corpus']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
