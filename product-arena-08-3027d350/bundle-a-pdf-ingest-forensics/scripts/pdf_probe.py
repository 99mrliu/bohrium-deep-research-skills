#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pdf_probe.py — forensic intake probe for PDF inputs (stdlib only).

Two input modes:
  1) Real PDF bytes : python3 pdf_probe.py paper.pdf --out OUTDIR
  2) Page manifest  : python3 pdf_probe.py --manifest pages.json --out OUTDIR
     (synthetic page inventory; lets the full triage logic run without a PDF)

What it checks (BEFORE any content parsing is attempted):
  * encryption marker (/Encrypt)          -> hard stop, never parse garbage
  * page object count                     -> is this even a paged document?
  * /Rotate values / MediaBox             -> rotation anomalies
  * image XObjects vs. text-show ops      -> scanned-document suspicion
  * per-page text-layer coverage          -> digital vs. scanned pages
      - via PyMuPDF  (if importable)
      - via pdftotext (poppler, if on PATH)
      - via manifest fields (manifest mode)
  * duplicate pages                       -> identical page fingerprints

Output: OUTDIR/intake_report.json + a one-line JSON summary on stdout.
Exit codes: 0 = ok, 2 = partial (anomalies found, still routable),
            3 = failed (encrypted / not a PDF / no pages).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zlib

SCANNED_CHAR_THRESHOLD = 20  # <20 extracted chars on a page WITH images => scanned candidate

REPORT_SCHEMA = "pdf-ingest-forensics/intake_report/v1"


def _md5(text):
    data = text if isinstance(text, bytes) else text.encode("utf-8", "replace")
    return hashlib.md5(data).hexdigest()


# ---------------------------------------------------------------- raw probe
def raw_inspect(data):
    """Best-effort inspection of raw PDF bytes with the stdlib only."""
    info = {}
    info["header_ok"] = data[:5] == b"%PDF-"
    m = re.search(rb"%PDF-(\d\.\d)", data[:64])
    info["pdf_version"] = m.group(1).decode("ascii") if m else None
    # /Encrypt lives in the trailer dict; the name is distinctive enough that a
    # raw search is a reliable triage signal (we never decrypt, we stop).
    info["encrypted"] = bool(re.search(rb"/Encrypt\b", data))
    # count real page objects; negative lookahead keeps /Pages out
    info["page_objects"] = len(re.findall(rb"/Type\s*/Page(?![\w/])", data))
    info["rotate_values"] = sorted(
        {int(v) for v in re.findall(rb"/Rotate\s+(-?\d+)", data)})
    mb = re.search(rb"/MediaBox\s*\[([^\]]+)\]", data)
    info["mediabox_first"] = mb.group(1).decode("latin-1").strip() if mb else None
    info["image_xobjects"] = len(re.findall(rb"/Subtype\s*/Image\b", data))
    # inflate FlateDecode streams where possible and count text-show operators
    text_ops = 0
    streams = 0
    inflated = 0
    for sm in re.finditer(rb"stream\r?\n", data):
        end = data.find(b"endstream", sm.end())
        if end < 0:
            continue
        streams += 1
        raw = data[sm.end():end].rstrip(b"\r\n")
        try:
            decoded = zlib.decompress(raw)
            inflated += 1
        except Exception:
            decoded = raw  # uncompressed or foreign filter; scan raw bytes
        text_ops += len(re.findall(rb"\bTj\b|\bTJ\b", decoded))
    info["streams_total"] = streams
    info["streams_inflated"] = inflated
    info["text_show_ops"] = text_ops
    return info


# ------------------------------------------------- optional external tooling
def measure_with_pymupdf(path):
    """Per-page char counts / images / rotation via PyMuPDF, if importable."""
    try:
        import fitz  # PyMuPDF
    except Exception:
        return None
    try:
        doc = fitz.open(path)
    except Exception as exc:
        return {"error": "pymupdf_open_failed: %s" % exc}
    if getattr(doc, "needs_pass", False):
        return {"encrypted": True, "pages": []}
    pages = []
    for i, page in enumerate(doc, 1):
        text = page.get_text("text") or ""
        norm = " ".join(text.split())
        pages.append({
            "page": i,
            "width": round(float(page.rect.width), 1),
            "height": round(float(page.rect.height), 1),
            "rotate": int(page.rotation),
            "image_count": len(page.get_images(full=True)),
            "char_count": len(norm),
            "fingerprint": _md5(norm) if norm else None,
        })
    doc.close()
    return {"encrypted": False, "pages": pages}


def measure_with_pdftotext(path, page_count):
    """Per-page char counts via poppler's pdftotext, if on PATH."""
    exe = shutil.which("pdftotext")
    if not exe or page_count < 1:
        return None
    pages = []
    for i in range(1, page_count + 1):
        try:
            r = subprocess.run(
                [exe, "-f", str(i), "-l", str(i), "-enc", "UTF-8", path, "-"],
                capture_output=True, timeout=120)
            text = r.stdout.decode("utf-8", "replace")
        except Exception:
            text = ""
        norm = " ".join(text.split())
        pages.append({
            "page": i,
            "width": None,
            "height": None,
            "rotate": None,
            "image_count": None,
            "char_count": len(norm),
            "fingerprint": _md5(norm) if norm else None,
        })
    return {"encrypted": False, "pages": pages}


# ------------------------------------------------------------- classification
def classify_pages(pages):
    """Attach per-page forensic flags. `pages` is a list of dicts with at
    least: page, char_count (None = unknown), image_count (None = unknown),
    rotate (None = unknown), fingerprint (None = no text)."""
    for p in pages:
        flags = []
        cc = p.get("char_count")
        ic = p.get("image_count")
        rot = p.get("rotate")
        if ic and ic >= 1 and cc is not None and cc < SCANNED_CHAR_THRESHOLD:
            flags.append("scanned_candidate")
        if cc is not None and cc == 0 and not ic:
            flags.append("empty_page")
        if rot is not None and (rot % 360) != 0:
            flags.append("rotated")
        p["flags"] = flags
        p["duplicate_of"] = None
    # duplicate detection: identical non-empty fingerprints
    seen = {}
    for p in pages:
        fp = p.get("fingerprint")
        if not fp:
            continue
        if fp in seen:
            p["duplicate_of"] = seen[fp]
            p["flags"].append("duplicate_page")
        else:
            seen[fp] = p["page"]
    return pages


def build_report(source, encrypted, pages, raw, measure_tool, measured, extra_reasons):
    reasons = list(extra_reasons)
    limitations = []
    if not measured:
        limitations.append(
            "text-layer coverage NOT measured per page (no pymupdf / pdftotext / "
            "manifest); treat coverage as unknown")
    if raw is not None and not raw.get("header_ok"):
        reasons.append("file does not start with %PDF- header")

    scanned = [p["page"] for p in pages if "scanned_candidate" in p["flags"]]
    rotated = [p["page"] for p in pages if "rotated" in p["flags"]]
    empties = [p["page"] for p in pages if "empty_page" in p["flags"]]
    dup_pairs = [[p["duplicate_of"], p["page"]] for p in pages
                 if p.get("duplicate_of")]

    if encrypted:
        status = "failed"
        reasons.append("encrypted_pdf: /Encrypt marker present; refusing to parse")
    elif not pages:
        status = "failed"
        reasons.append("no_pages: zero page objects found")
    elif scanned or rotated or dup_pairs or not measured or raw is not None and not raw.get("header_ok"):
        status = "partial"
        if scanned:
            reasons.append("scanned_pages: %s have images but <%d chars"
                           % (scanned, SCANNED_CHAR_THRESHOLD))
        if rotated:
            reasons.append("rotated_pages: %s carry non-zero /Rotate" % rotated)
        if dup_pairs:
            reasons.append("duplicate_pages: %s" % dup_pairs)
    else:
        status = "ok"

    return {
        "schema": REPORT_SCHEMA,
        "tool": "pdf_probe.py",
        "source": source,
        "status": status,
        "reasons": reasons,
        "encrypted": bool(encrypted),
        "page_count": len(pages),
        "pages": pages,
        "summary": {
            "measure_tool": measure_tool,
            "text_layer_measured": bool(measured),
            "scanned_pages": scanned,
            "rotated_pages": rotated,
            "empty_pages": empties,
            "duplicate_pairs": dup_pairs,
        },
        "raw_container": raw,
        "limitations": limitations,
    }


# -------------------------------------------------------------------- modes
def run_manifest(manifest_path):
    with open(manifest_path, "r", encoding="utf-8") as fh:
        man = json.load(fh)
    pages = []
    for i, p in enumerate(man.get("pages", []), 1):
        pages.append({
            "page": int(p.get("page", i)),
            "width": p.get("width"),
            "height": p.get("height"),
            "rotate": p.get("rotate", 0),
            "image_count": p.get("image_count", 0),
            "char_count": p.get("char_count"),
            "fingerprint": p.get("fingerprint"),
        })
    pages = classify_pages(pages)
    return build_report(
        source={"mode": "manifest", "path": os.path.abspath(manifest_path),
                "note": man.get("note", "")},
        encrypted=bool(man.get("encrypted", False)),
        pages=pages, raw=None,
        measure_tool="manifest", measured=True, extra_reasons=[])


def run_pdf(pdf_path):
    with open(pdf_path, "rb") as fh:
        data = fh.read()
    raw = raw_inspect(data)
    if raw["encrypted"]:
        return build_report(
            source={"mode": "pdf", "path": os.path.abspath(pdf_path)},
            encrypted=True, pages=[], raw=raw,
            measure_tool="raw-only", measured=False, extra_reasons=[])

    measured = measure_with_pymupdf(pdf_path)
    tool = "pymupdf"
    if measured is None or "error" in measured:
        err = measured.get("error") if isinstance(measured, dict) else None
        measured = measure_with_pdftotext(pdf_path, raw["page_objects"])
        tool = "pdftotext"
        if measured is None and err:
            raw.setdefault("tool_errors", []).append(err)
    if measured is not None and measured.get("encrypted"):
        return build_report(
            source={"mode": "pdf", "path": os.path.abspath(pdf_path)},
            encrypted=True, pages=[], raw=raw,
            measure_tool=tool, measured=False, extra_reasons=[])

    extra = []
    if measured is None:
        tool = "raw-only"
        pages = []
        # fall back to container-level suspicion only
        if raw["image_xobjects"] > 0 and raw["text_show_ops"] == 0:
            extra.append("container shows images but no text-show operators; "
                         "whole document is a scanned candidate (unverified per page)")
    else:
        pages = classify_pages(measured["pages"])
    return build_report(
        source={"mode": "pdf", "path": os.path.abspath(pdf_path)},
        encrypted=False, pages=pages, raw=raw,
        measure_tool=tool, measured=measured is not None, extra_reasons=extra)


# --------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Forensic intake probe for PDF inputs (stdlib only).")
    ap.add_argument("pdf", nargs="?", help="path to a real PDF file")
    ap.add_argument("--manifest", help="synthetic page inventory JSON "
                                       "(runs without a real PDF)")
    ap.add_argument("--out", default=".",
                    help="output directory for intake_report.json")
    args = ap.parse_args(argv)

    if not args.pdf and not args.manifest:
        ap.error("give a PDF path or --manifest pages.json")
    if args.pdf and args.manifest:
        ap.error("give either a PDF path or --manifest, not both")

    os.makedirs(args.out, exist_ok=True)
    if args.manifest:
        report = run_manifest(args.manifest)
    else:
        if not os.path.isfile(args.pdf):
            print(json.dumps({"status": "failed",
                              "reasons": ["file_not_found: %s" % args.pdf]}))
            return 3
        report = run_pdf(args.pdf)

    out_path = os.path.join(args.out, "intake_report.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")

    summary = {
        "status": report["status"],
        "reasons": report["reasons"],
        "page_count": report["page_count"],
        "scanned_pages": report["summary"]["scanned_pages"],
        "rotated_pages": report["summary"]["rotated_pages"],
        "duplicate_pairs": report["summary"]["duplicate_pairs"],
        "report": out_path,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return {"ok": 0, "partial": 2, "failed": 3}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
