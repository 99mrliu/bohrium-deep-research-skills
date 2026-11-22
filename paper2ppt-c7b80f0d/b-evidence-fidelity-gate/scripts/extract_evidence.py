#!/usr/bin/env python3
"""extract_evidence.py -- PASS 1 of the evidence fidelity gate.

Builds a structured evidence index from the *actual* paper PDF using only the
Python 3 standard library plus the external poppler tools `pdftotext` and
`pdftoppm` (located via PATH; a clear error is emitted if they are missing).

Outputs (all under --outdir):
  paper_pages.json      list of {"page": int, "text": str}  (raw -layout text per page)
  paper.txt             all pages concatenated, separated by formfeed (\f)
  evidence_index.json   sections / figures / tables / in_text_refs / fact_pool
  pages/page-*.png      page renders (default 150 dpi) for visual confirmation

Fields marked "heuristic": true are produced by regex heuristics and MUST be
visually confirmed against pages/page-*.png before they are relied on.

Exit codes: 0 success; 2 missing tool or unreadable input; 1 extraction failure.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

# --------------------------------------------------------------------------
# Number/unit machinery (kept consistent with check_plan.py / audit_deck.py).
# A "number token" is an optional-signed decimal with optional thousands
# commas, optional scientific suffix ("3.2 x 10^5", "1e-4"), and an optional
# immediately following unit. Unicode micro signs are normalized to "u".
# --------------------------------------------------------------------------
UNITS = [
    "percent", "%", "°C", "K",
    "ms", "μs", "µs", "us", "ns", "ps", "sec", "s", "min", "h", "hr",
    "eV", "keV", "MeV", "GeV", "TeV",
    "nm", "μm", "µm", "um", "mm", "cm", "km", "m",
    "mM", "μM", "µM", "uM", "nM", "pM", "mol", "mmol", "μmol", "umol",
    "mg", "μg", "µg", "ug", "kg", "g",
    "THz", "GHz", "MHz", "kHz", "Hz",
    "mL", "μL", "µL", "uL", "L", "dB",
    "mV", "kV", "V", "mA", "μA", "uA", "A", "mW", "kW", "MW", "W",
    "kPa", "MPa", "GPa", "Pa", "bar", "atm", "rpm",
    "KB", "MB", "GB", "TB", "dpi", "fps", "bp", "kb", "Mb",
    # pseudo-units: counting words that make a bare integer a factual claim
    "epochs", "epoch", "samples", "sample", "subjects", "subject",
    "patients", "patient", "layers", "layer", "folds", "fold",
    "trials", "trial", "runs", "run", "GPUs", "GPU",
]
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(set(UNITS), key=len, reverse=True))
_NUMBER = r"[-+]?\d+(?:,\d{3})*(?:\.\d+)?(?:\s*[×x]\s*10\^?[-+]?\d+|[eE][-+]?\d+)?"
TOKEN_RE = re.compile(
    r"(?<![\w.])(?P<num>" + _NUMBER + r")(?:\s*(?P<unit>" + _UNIT_ALT + r"))?(?![\w%])"
)

LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "–": "-", "−": "-"}


def norm_text(s):
    """Whitespace + ligature normalization used for verbatim matching."""
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return " ".join(s.split())


def find_tool(name):
    path = shutil.which(name)
    if not path:
        sys.stderr.write(
            "ERROR: required tool '%s' not found on PATH. Install poppler "
            "(pdf-text-tool / pdf-render-tool in environment/resources.yaml).\n" % name
        )
        sys.exit(2)
    return path


def run(cmd, what):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except OSError as e:
        sys.stderr.write("ERROR: failed to run %s: %s\n" % (what, e))
        sys.exit(1)
    if proc.returncode != 0:
        sys.stderr.write("ERROR: %s failed (rc=%d): %s\n" % (what, proc.returncode, proc.stderr.strip()))
        sys.exit(1)
    return proc


# --------------------------------------------------------------------------
# Heuristic extractors
# --------------------------------------------------------------------------
SEC_NUM_RE = re.compile(r"^\s*(\d+(?:\.\d+)*\.?)\s+([A-Z][A-Za-z0-9 ,&\-:()]{2,70})\s*$")
SEC_CAP_RE = re.compile(r"^\s*([A-Z][A-Z ,&\-]{3,60})\s*$")

CAP_START_RE = re.compile(
    r"^\s*(Figure|Fig\.?|FIG\.?|Table|TABLE)\s*(\d+)\s*[:.)]\s*(.+)$"
)
REF_RE = re.compile(r"(?<![\w])(?:Fig\.?|Figure|FIG\.?|Table|TABLE)\s*\d+[a-z]?")


def extract_sections(pages):
    """Heuristic: numbered headings ('2. Method') or ALL-CAPS lines."""
    seen, out = set(), []
    for pno, text in pages:
        for line in text.splitlines():
            m = SEC_NUM_RE.match(line)
            if m:
                key = (m.group(1), m.group(2).strip())
                if key not in seen:
                    seen.add(key)
                    out.append({"number": m.group(1), "title": m.group(2).strip(),
                                "page": pno, "heuristic": True})
                continue
            m = SEC_CAP_RE.match(line)
            if m and len(m.group(1).split()) <= 8:
                key = ("", m.group(1).strip())
                if key not in seen:
                    seen.add(key)
                    out.append({"number": "", "title": m.group(1).strip(),
                                "page": pno, "heuristic": True})
    return out


def extract_captions(pages):
    """Heuristic: 'Figure 1: ...' / 'TABLE 2. ...' caption blocks.

    Continuation lines (wrapped caption text) are joined until a blank line,
    another caption start, or a line that looks like body text column.
    """
    figures, tables = [], []
    for pno, text in pages:
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            m = CAP_START_RE.match(lines[i])
            if m:
                kind_raw, num, first = m.group(1), m.group(2), m.group(3).strip()
                cap_lines = [first]
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if not nxt.strip() or CAP_START_RE.match(nxt):
                        break
                    # stop if the line looks like a new section heading
                    if SEC_NUM_RE.match(nxt) or SEC_CAP_RE.match(nxt):
                        break
                    cap_lines.append(nxt.strip())
                    j += 1
                caption = norm_text(" ".join(cap_lines))
                entry = {"id": num, "caption": caption, "page": pno, "heuristic": True}
                (tables if kind_raw.lower().startswith("table") else figures).append(entry)
                i = j
            else:
                i += 1
    return figures, tables


def extract_refs(pages):
    """All in-text 'Fig. 2' / 'Table 1' style occurrences (heuristic)."""
    refs = []
    for pno, text in pages:
        flat = norm_text(text)
        for m in REF_RE.finditer(flat):
            ctx = flat[max(0, m.start() - 40): m.end() + 40]
            refs.append({"ref": m.group(0), "page": pno,
                         "context": ctx, "heuristic": True})
    return refs


def extract_fact_pool(pages):
    """Sentences containing a number+unit token or a percent (the fact pool).

    Pages are flattened and split into sentences; a sentence joins the pool if
    it contains at least one number token carrying a unit (incl. '%') or a
    scientific-notation number. Heuristic: sentence splitting is regex-based.
    """
    pool = []
    sent_split = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
    for pno, text in pages:
        flat = norm_text(text)
        for sent in sent_split.split(flat):
            keep = False
            for tm in TOKEN_RE.finditer(sent):
                if tm.group("unit") or ("10^" in tm.group("num")) or ("e" in tm.group("num").lower() and any(c.isdigit() for c in tm.group("num").split("e")[-1]) and ("e+" in tm.group("num").lower() or "e-" in tm.group("num").lower())):
                    keep = True
                    break
            if keep:
                pool.append({"page": pno, "sentence": sent, "heuristic": True})
    return pool


def main():
    ap = argparse.ArgumentParser(description="Extract evidence index from a paper PDF (PASS 1).")
    ap.add_argument("--pdf", required=True, help="path to the paper PDF")
    ap.add_argument("--outdir", default="/app/work", help="working directory for outputs")
    ap.add_argument("--dpi", type=int, default=150, help="render dpi for page PNGs")
    ap.add_argument("--no-render", action="store_true", help="skip pdftoppm page renders")
    args = ap.parse_args()

    if not os.path.isfile(args.pdf):
        sys.stderr.write("ERROR: PDF not found: %s\n" % args.pdf)
        sys.exit(2)

    pdftotext = find_tool("pdftotext")
    pdftoppm = None if args.no_render else find_tool("pdftoppm")

    os.makedirs(args.outdir, exist_ok=True)
    raw_path = os.path.join(args.outdir, "paper_raw.txt")
    run([pdftotext, "-layout", "-enc", "UTF-8", args.pdf, raw_path], "pdftotext")

    with open(raw_path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    pages_raw = raw.split("\f")
    while pages_raw and not pages_raw[-1].strip():
        pages_raw.pop()
    if not pages_raw:
        sys.stderr.write("ERROR: pdftotext produced no text. The PDF may be "
                         "scanned/encrypted -- use the ocr-tool and re-run on the OCR text.\n")
        sys.exit(1)

    pages = [(i + 1, t) for i, t in enumerate(pages_raw)]

    with open(os.path.join(args.outdir, "paper_pages.json"), "w", encoding="utf-8") as f:
        json.dump([{"page": p, "text": t} for p, t in pages], f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.outdir, "paper.txt"), "w", encoding="utf-8") as f:
        f.write("\f".join(t for _, t in pages))

    figures, tables = extract_captions(pages)
    index = {
        "source_pdf": os.path.abspath(args.pdf),
        "n_pages": len(pages),
        "sections": extract_sections(pages),
        "figures": figures,
        "tables": tables,
        "in_text_refs": extract_refs(pages),
        "fact_pool": extract_fact_pool(pages),
        "notes": "Fields marked heuristic=true come from regex heuristics on "
                 "pdftotext -layout output; confirm captions against pages/page-*.png "
                 "before citing them on slides.",
    }
    with open(os.path.join(args.outdir, "evidence_index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    rendered = []
    if pdftoppm:
        pages_dir = os.path.join(args.outdir, "pages")
        os.makedirs(pages_dir, exist_ok=True)
        prefix = os.path.join(pages_dir, "page")
        run([pdftoppm, "-png", "-r", str(args.dpi), args.pdf, prefix], "pdftoppm")
        rendered = sorted(os.path.join("pages", n) for n in os.listdir(pages_dir) if n.endswith(".png"))

    sys.stdout.write(json.dumps({
        "status": "ok",
        "pages": len(pages),
        "sections": len(index["sections"]),
        "figures": len(figures),
        "tables": len(tables),
        "fact_pool_sentences": len(index["fact_pool"]),
        "rendered_pages": len(rendered),
        "outdir": os.path.abspath(args.outdir),
    }, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
