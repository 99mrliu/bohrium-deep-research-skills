#!/usr/bin/env python3
"""sectionize.py -- split a paper into sections and paragraph anchors.

Anchor scheme (independent of any other tool): ``s<section>¶<paragraph>``,
1-based. Sections come from headings (numbered or known names); paragraphs
are blank-line-separated blocks inside a section. Output sections.json:

  {"doc_id", "sha256", "backend",
   "sections": [{"sid": 1, "title": ..., "anchor": "s1",
                 "paragraphs": [{"anchor": "s1¶1", "text": ...}, ...]}]}

Backends: pdftotext (plain) when given --pdf, else --text-file. Standard
library only. Extraction failures produce a minimal sections.json with a
single ``unparsed`` pseudo-section and a warning instead of a crash.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

KNOWN = {
    "abstract", "introduction", "background", "related work", "methods",
    "method", "materials and methods", "methodology", "experiments",
    "experimental setup", "results", "results and discussion", "discussion",
    "conclusion", "conclusions", "limitations", "references",
    "acknowledgements", "acknowledgments", "appendix",
}
NUM_HEAD = re.compile(r"^(\d+(?:\.\d+)*)[.)]?\s+(\S.*)$")


def looks_heading(line):
    t = re.sub(r"\s+", " ", line).strip()
    if not t or len(t) > 110:
        return None
    if t.lower().strip(".: ") in KNOWN:
        return t
    m = NUM_HEAD.match(t)
    if m and len(m.group(2)) > 2 and (m.group(2)[0].isupper() or m.group(2).isupper()):
        return t
    return None


def extract_text(args, out):
    if args.text_file:
        with open(args.text_file, "rb") as fh:
            raw = fh.read()
        return raw.decode("utf-8", errors="replace"), raw, "text-file", None
    with open(args.pdf, "rb") as fh:
        raw = fh.read()
    if not shutil.which("pdftotext"):
        return None, raw, None, "pdftotext not on PATH; use --text-file with the platform export"
    out_txt = os.path.join(out, "plain.txt")
    proc = subprocess.run(["pdftotext", args.pdf, out_txt],
                          capture_output=True, text=True, timeout=240)
    if proc.returncode != 0:
        return None, raw, None, "pdftotext failed: " + proc.stderr.strip()[:300]
    with open(out_txt, encoding="utf-8", errors="replace") as fh:
        return fh.read(), raw, "pdftotext-plain", None


def sectionize(text):
    pages = text.split("\f")
    blocks = []
    for pno, page in enumerate(pages, start=1):
        buf = []
        for raw in page.splitlines():
            line = raw.rstrip()
            if line.strip() == "":
                if buf:
                    blocks.append((pno, buf))
                    buf = []
            else:
                buf.append(line.strip())
        if buf:
            blocks.append((pno, buf))
    sections = []
    cur = {"title": "front matter", "paragraphs": []}
    in_refs = False
    for pno, lines in blocks:
        first = lines[0]
        head = looks_heading(first) if len(first) < 110 else None
        if head and (len(first) > 60 or first.rstrip().endswith((".", ",", ";", ":"))):
            head = None  # likely a sentence that merely starts with digits
        if head:
            if in_refs and NUM_HEAD.match(head):
                pass  # numbered bibliography entries are not new sections
            else:
                if cur["paragraphs"] or cur["title"] != "front matter":
                    sections.append(cur)
                cur = {"title": head, "paragraphs": []}
                if head.lower().strip(".: ") == "references":
                    in_refs = True
                rest = [r for r in lines[1:] if r.strip()]
                if rest:
                    cur["paragraphs"].append({"page": pno, "text": " ".join(rest)})
                continue
        cur["paragraphs"].append({"page": pno, "text": " ".join(lines)})
    if cur["paragraphs"]:
        sections.append(cur)
    if not sections:
        sections = [{"title": "unparsed", "paragraphs": []}]
    out_sections = []
    for sid, sec in enumerate(sections, start=1):
        paras = [{"anchor": "s%d¶%d" % (sid, i), "page": p["page"], "text": p["text"]}
                 for i, p in enumerate(sec["paragraphs"], start=1)]
        out_sections.append({"sid": sid, "title": sec["title"],
                             "anchor": "s%d" % sid, "paragraphs": paras})
    return out_sections


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf")
    ap.add_argument("--text-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--case-id", default="doc")
    args = ap.parse_args()
    if not args.pdf and not args.text_file:
        ap.error("one of --pdf / --text-file is required")
    os.makedirs(args.out, exist_ok=True)
    text, raw, backend, error = extract_text(args, args.out)
    if text is None:
        result = {"doc_id": args.case_id, "sha256": hashlib.sha256(raw).hexdigest(),
                  "backend": None, "status": "unreadable", "reason": error,
                  "handover": "export text with the platform PDF/OCR tools and rerun "
                              "with --text-file", "sections": []}
    else:
        result = {"doc_id": args.case_id, "sha256": hashlib.sha256(raw).hexdigest(),
                  "backend": backend, "status": "ok",
                  "sections": sectionize(text)}
    with open(os.path.join(args.out, "sections.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    print(json.dumps({"status": result["status"], "backend": backend,
                      "sections": len(result["sections"])}, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 3


if __name__ == "__main__":
    sys.exit(main())
