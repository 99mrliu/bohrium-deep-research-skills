#!/usr/bin/env python3
"""caption_parse.py — parse a figure caption into per-panel clauses.

Caption text source priority:
  1. --caption FILE            (explicit, wins)
  2. caption fields in --case  (case.json)
  3. pdftotext blocks from PDFs in --input-dir matching /^\\s*(Figure|Fig\\.)/
     (absence of pdftotext -> degraded flag)

Tokenizes panel references ((a), panel A, Fig. 1c, ranges "(a)-(c)"), splits the
caption into sentences, assigns each sentence to its panel(s); leading overview
sentences belong to all panels. Figures referenced but whose pixels are not in the
materials list are recorded as gap-ledger seeds.

CLI: --case CASE.json --task TASK.md [--caption FILE] [--input-dir DIR] --work DIR

Exit codes: 0 = clean, 2 = success with warnings, 1 = fatal error.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
PANEL_REF_RE = re.compile(
    r"\(([a-zA-Z]{1,2})\)"                 # (a)  (b)  (iv)
    r"|\bpanel\s+([A-Za-z])\b"             # panel A
    r"|\bFig(?:ure)?\.?\s*\d+\s*([a-z])\b"  # Fig. 1c
)
RANGE_RE = re.compile(r"\(([a-zA-Z])\)\s*[\u2013\u2014-]\s*\(([a-zA-Z])\)")
FIGURE_RE = re.compile(r"\bFig(?:ure)?s?\.?\s*(\d+)")
CAPTION_START_RE = re.compile(r"^\s*(Figure|Fig\.)")
PROTECTED = ["Fig.", "fig.", "vs.", "et al.", "e.g.", "i.e.", "cf.", "No."]


def fatal(msg):
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_case(path):
    if not path:
        return None
    if not os.path.isfile(path):
        fatal(f"case file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:  # noqa: BLE001
        fatal(f"cannot parse case file {path}: {exc}")


def find_caption_in_case(obj):
    """First string value under a key containing 'caption' (DFS, longest wins)."""
    hits = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if isinstance(v, str) and "caption" in str(k).lower():
                    hits.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(obj)
    return max(hits, key=len) if hits else None


def caption_from_pdfs(input_dir):
    """Return (text_or_None, degraded_bool)."""
    if not input_dir or not os.path.isdir(input_dir):
        return None, False
    pdfs = sorted(f for f in os.listdir(input_dir) if f.lower().endswith(".pdf"))
    if not pdfs:
        return None, False
    if shutil.which("pdftotext") is None:
        return None, True
    blocks = []
    for pdf in pdfs:
        try:
            out = subprocess.run(
                ["pdftotext", os.path.join(input_dir, pdf), "-"],
                capture_output=True, text=True, timeout=60, check=False)
        except Exception:  # noqa: BLE001
            continue
        if out.returncode != 0:
            continue
        for para in re.split(r"\n\s*\n", out.stdout):
            flat = " ".join(para.split())
            if CAPTION_START_RE.match(flat):
                blocks.append(flat)
    return ("\n".join(blocks) if blocks else None), False


def material_paths(case):
    mats = (case or {}).get("materials", [])
    paths = []
    for m in mats:
        if isinstance(m, str):
            paths.append(m)
        elif isinstance(m, dict):
            for key in ("path", "file", "name", "filename"):
                if key in m and isinstance(m[key], str):
                    paths.append(m[key])
                    break
    return paths


def figures_with_pixels(materials):
    """Set of figure numbers that have a shipped image file."""
    numbers = set()
    for m in materials:
        base = os.path.basename(m).lower()
        if os.path.splitext(base)[1] not in IMAGE_EXT:
            continue
        for match in re.finditer(r"fig(?:ure)?[\s_\-]*0*(\d+)", base):
            numbers.add(int(match.group(1)))
    return numbers


def split_sentences(text):
    protected = text
    for i, tok in enumerate(PROTECTED):
        protected = protected.replace(tok, tok[:-1] + f"\x00{i}")
    parts = re.split(r"(?<=[.!?])\s+", protected.strip())
    sentences = []
    for part in parts:
        s = part.strip()
        for i, tok in enumerate(PROTECTED):
            s = s.replace(tok[:-1] + f"\x00{i}", tok)
        if s:
            sentences.append(s)
    return sentences


def expand_ranges(sentence):
    letters = set()
    for a, b in RANGE_RE.findall(sentence):
        lo, hi = ord(a.lower()), ord(b.lower())
        if lo < hi and hi - lo <= 20:
            for c in range(lo, hi + 1):
                letters.add(chr(c))
    return letters


def panel_refs_in(sentence):
    refs = expand_ranges(sentence)
    ordered = []
    for match in PANEL_REF_RE.finditer(sentence):
        letter = next(g for g in match.groups() if g)
        if len(letter) == 2 and letter.lower() not in ("iv", "ii", "iii"):
            # two-letter parentheticals are usually not panel refs; skip unless range
            continue
        letter = letter.lower()
        if letter not in ordered:
            ordered.append(letter)
    for letter in sorted(expand_ranges(sentence)):
        if letter not in ordered:
            ordered.append(letter)
    return ordered


def main():
    ap = argparse.ArgumentParser(description="Parse a figure caption into per-panel clauses.")
    ap.add_argument("--case", default=None)
    ap.add_argument("--task", required=True)
    ap.add_argument("--caption", default=None)
    ap.add_argument("--input-dir", default=None)
    ap.add_argument("--work", required=True)
    args = ap.parse_args()

    if not os.path.isfile(args.task):
        fatal(f"task file not found: {args.task}")
    os.makedirs(args.work, exist_ok=True)
    case = load_case(args.case)
    warnings = []

    caption_text, source, degraded = None, "none", False
    if args.caption:
        if not os.path.isfile(args.caption):
            fatal(f"caption file not found: {args.caption}")
        with open(args.caption, "r", encoding="utf-8") as fh:
            caption_text = fh.read().strip()
        source = "explicit_file"
    if caption_text is None and case is not None:
        caption_text = find_caption_in_case(case)
        if caption_text:
            source = "case_json"
    if caption_text is None:
        caption_text, degraded = caption_from_pdfs(args.input_dir)
        if caption_text:
            source = "pdftotext"
        elif degraded:
            warnings.append("degraded: pdftotext not available; PDF caption extraction skipped")
    if caption_text is None:
        caption_text = ""
        warnings.append("caption_missing: link against task.md only")

    sentences = split_sentences(caption_text) if caption_text else []
    clauses = {}
    overview, unassigned = [], []
    panel_refs = []
    seen_panel_sentence = False
    for sent in sentences:
        refs = panel_refs_in(sent)
        if refs:
            seen_panel_sentence = True
            for letter in refs:
                clauses.setdefault(letter, []).append(sent)
                if letter not in panel_refs:
                    panel_refs.append(letter)
        elif not seen_panel_sentence:
            overview.append(sent)
        else:
            unassigned.append(sent)
    if unassigned:
        warnings.append(f"unassigned_clauses: {len(unassigned)} sentence(s) mention no panel")

    materials = material_paths(case)
    have_pixels = figures_with_pixels(materials)
    referenced = []
    for match in FIGURE_RE.finditer(caption_text):
        n = int(match.group(1))
        if n not in referenced:
            referenced.append(n)
    gaps = []
    for n in referenced:
        if n not in have_pixels:
            gaps.append({
                "reference": f"Figure {n}",
                "mentioned_in": "caption",
                "reason": "referenced in caption but no image pixels shipped in materials",
            })
    if gaps:
        warnings.append(f"figures_without_pixels: {', '.join(g['reference'] for g in gaps)}")

    caption_map = {
        "schema": "caption_map/1",
        "caption_source": source + (" (degraded)" if degraded else ""),
        "caption_text": caption_text,
        "panel_refs": panel_refs,
        "clauses": clauses,
        "overview_clauses": overview,
        "unassigned_clauses": unassigned,
        "figures_referenced": [f"Figure {n}" for n in referenced],
        "figures_with_pixels": sorted(f"Figure {n}" for n in have_pixels),
        "figures_without_pixels": gaps,
        "warnings": warnings,
    }
    out_path = os.path.join(args.work, "caption_map.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(caption_map, fh, ensure_ascii=False, indent=2)
    print(f"wrote {out_path}: {len(panel_refs)} panel ref(s), "
          f"{len(gaps)} figure(s) without pixels")
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    sys.exit(2 if warnings else 0)


if __name__ == "__main__":
    main()
