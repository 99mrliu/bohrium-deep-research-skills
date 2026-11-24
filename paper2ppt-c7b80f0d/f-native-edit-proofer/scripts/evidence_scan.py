#!/usr/bin/env python3
"""evidence_scan.py -- verbatim quote hit-scan for ppt-native-edit-proofer.

Extracts full text from the source PDF (chain: pdftotext -> pymupdf -> pypdf)
and verifies that every quote declared in deck.json appears verbatim
(whitespace-normalized). Backs the content_map[*].sources[*].quote fields
with real evidence instead of assertion.

Usage:
    python3 evidence_scan.py --paper paper.pdf --deck deck.json \
        --report evidence_scan.json
Exit code 1 if any quote misses.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys


def norm(s):
    return re.sub(r"\s+", " ", s or "").strip()


def extract_pdf_text(path):
    """Return (text, engine). Degradation chain, never raises."""
    # 1) pdftotext
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(
                ["pdftotext", "-q", path, "-"],
                capture_output=True, text=True, timeout=60)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout, "pdftotext"
        except (OSError, subprocess.SubprocessError):
            pass
    # 2) pymupdf
    try:
        import pymupdf  # type: ignore
        doc = pymupdf.open(path)
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text, "pymupdf"
    except ImportError:
        pass
    except Exception:
        pass
    # 3) pypdf
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(path)
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        if text.strip():
            return text, "pypdf"
    except ImportError:
        pass
    except Exception:
        pass
    return "", "none"


def iter_quotes(deck):
    """Yield (slide_no, locator, quote) from every claim/source in deck.json."""
    for i, slide in enumerate(deck.get("slides", []), start=1):
        for b in slide.get("bullets", []):
            if isinstance(b, dict) and b.get("quote"):
                src = b.get("source", {})
                yield i, src.get("locator", "?"), b["quote"]
        cap = (slide.get("table") or {}).get("caption_quote")
        if cap:
            yield i, "table-caption", cap
        for ev in slide.get("evidence", []):
            if ev.get("quote"):
                yield i, ev.get("locator", "?"), ev["quote"]


def main():
    ap = argparse.ArgumentParser(description="Verify deck.json quotes appear "
                                     "verbatim in the source PDF text.")
    ap.add_argument("--paper", required=True)
    ap.add_argument("--deck", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()

    with open(args.deck, encoding="utf-8") as fh:
        deck = json.load(fh)
    text, engine = extract_pdf_text(args.paper)
    haystack = norm(text)

    checks, misses = [], 0
    for slide_no, locator, quote in iter_quotes(deck):
        hit = norm(quote) in haystack if haystack else False
        checks.append({"slide": slide_no, "locator": locator,
                       "quote": quote, "verbatim_hit": hit})
        if not hit:
            misses += 1
    total = len(checks)
    coverage = (total - misses) / total if total else 1.0

    report = {
        "paper": os.path.basename(args.paper),
        "extract_engine": engine,
        "extract_chars": len(text),
        "quotes_total": total,
        "quotes_hit": total - misses,
        "coverage": round(coverage, 4),
        "checks": checks,
    }
    os.makedirs(os.path.dirname(os.path.abspath(args.report)), exist_ok=True)
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print("evidence_scan: engine=%s quotes=%d hit=%d coverage=%.3f -> %s"
          % (engine, total, total - misses, coverage, args.report))
    if engine == "none":
        print("evidence_scan: ERROR no PDF text extractor available",
              file=sys.stderr)
        return 2
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
